Title: SQLite concurrent writes and "database is locked" errors
Date: 2025-02-01 12:18
Tags: SQLite, databases
Summary: SQLite [claims](https://www.sqlite.org/mostdeployed.html) to be one of the most popular pieces of software in the world, being integrated into every major operating system and browser. It became the ultimate database for client side apps. In recent years, there's also been a [growing interest in using SQLite on the backend](https://fly.io/blog/all-in-on-sqlite-litestream/). If you do this, you better keep in mind a major SQLite limitation: concurrent writes.<br><br>SQLite handles concurrent writes with a global write lock allowing only one writer at a time. If you have many concurrent write transactions, some will take a long time and some may even fail with the "database is locked" error. What I'd like to do in this post is to better understand how concurrent writes impact SQLite performance, how many are ok, and how we can improve it.

SQLite [claims](https://www.sqlite.org/mostdeployed.html) to be one of the most popular pieces of software in the world, being integrated into every major operating system and browser. It became the ultimate database for client-side apps. In recent years, there's also been a [growing interest in using SQLite on the backend](https://fly.io/blog/all-in-on-sqlite-litestream/). If you do this, you better keep in mind a major SQLite limitation: concurrent writes.

SQLite handles concurrent writes with a global write lock allowing only one writer at a time. If you have many concurrent write transactions, some will take a long time and some may even fail with the "database is locked" error. What I'd like to do in this post is better understand how concurrent writes impact SQLite performance, how many are ok, and how we can improve it.

## SQLite background

We'll go deep, so let me quickly remind you of the most important facts [about SQLite](https://www.sqlite.org/about.html):

> SQLite is an embedded SQL database engine. Unlike most other SQL databases, SQLite does not have a separate server process. SQLite reads and writes directly to ordinary disk files. A complete SQL database with multiple tables, indices, triggers, and views, is contained in a single disk file. Think of SQLite not as a replacement for Oracle but as a replacement for `fopen()`.

> SQLite implements serializable transactions that are atomic, consistent, isolated, and durable, even if the transaction is interrupted by a program crash, an operating system crash, or a power failure to the computer.

I want to highlight that SQLite is just a [C library](https://www.sqlite.org/cintro.html). You include it, call `sqlite3_open()` to open a database file, `sqlite3_exec()` to execute SQL statements, and `sqlite3_close()` to close the database file. When you use SQLite from other languages, you typically use libraries that [wrap](https://docs.python.org/3/library/sqlite3.html) the SQLite C library or are [translated from it](https://pkg.go.dev/modernc.org/sqlite).

There is no server and no background processes. Clients operate on the database file. This is a crucial design decision aimed to **simplify architecture and reduce operational complexity**. SQLite takes this motto to heart. Keep it in mind. We'll see how it influences SQLite implementation and performance characteristics. Let's get started!

## Rollback mode vs WAL mode

SQLite can operate in two modes: using a [rollback journal](https://www.sqlite.org/lockingv3.html) or a [Write-Ahead Log (WAL)](https://www.sqlite.org/wal.html). These are two mechanisms to implement transactions, and they handle concurrent transactions very differently. The key difference is that in rollback mode, transactions modify the database file directly and "back up" original database content to a rollback journal in case the changes must be rolled back. With WAL, transactions append changes to the WAL file first, and at some point the changes are transferred from the WAL to the database file.

Both rollback mode and WAL mode allow multiple parallel readers and both allow one writer at a time. But WAL mode also supports having readers simultaneously with a writer, while in rollback mode, writers and readers block each other.

Rollback mode is legacy, but it's still the default for compatibility reasons and also because unlike WAL it works on NFS. WAL mode is more performant and unless you have a very specific reason, SQLite recommends enabling WAL mode. You can do that by issuing `PRAGMA journal_mode=WAL;`. We won't discuss rollback mode further and focus on WAL. If you're interested in rollback mode too, it's covered in the SQLite docs [here](https://www.sqlite.org/lockingv3.html) and [here](https://www.sqlite.org/atomiccommit.html).

**Note**: Beware that [some parts](https://www.sqlite.org/lang_transaction.html) of the SQLite docs describe the behavior of rollback mode without mentioning it explicitly. What's described may not be true for WAL mode.

## WAL mode overview

To see why certain transactions block each other while others don't, let me describe how reads and writes work in WAL mode. SQLite provides transaction isolation meaning that a transaction in progress doesn't see changes made by concurrent transactions. A read transaction "remembers" the database state at the point it started. In WAL mode, this is achieved by associating every read transaction with a point in the WAL called the end mark. Its meaning is that the transaction simply ignores new WAL changes appended after the end mark. The transaction reconstructs the database state from the database file and the WAL changes up to the end mark. Thus, there can be many readers, each having its own end mark and its own view of the database state. Writers do not interfere with readers because they simply append changes to the WAL.

One thing left: at some point the WAL changes must be transferred to the database file since read performance deteriorates as the WAL grows. This transferring process, also known as checkpointing, is automatic by default. If a write transaction makes the WAL grow above 1000 pages, that transaction performs checkpointing.

Checkpointing interferes with readers. It cannot transfer WAL changes that go after the end mark of any active transaction. If it did, it would update the database file with changes that the transaction should not see, violating isolation guarantees. So checkpointing runs only up to the first end mark. Another thing is that checkpointing cannot shrink the WAL while there are active readers. So it can run concurrently with readers, but it will never complete if there is always at least one active reader, and the WAL file will grow indefinitely. This problem is known as **checkpoint starvation**. It has multiple solutions including manual checkpointing. You can learn more about it and other WAL mode specifics in the [docs](https://www.sqlite.org/wal.html).

## Concurrent writes

> In most cases, a write transaction only takes milliseconds and so multiple writers can simply take turns.

This line from the [docs](https://www.sqlite.org/whentouse.html) summarizes how SQLite is supposed to handle concurrent writes. But it needs a very important comment. A write transaction holds the lock and blocks other writes during the entire write transaction duration. So if you have code that issues an insert and, before committing, performs some network calls, issues more SQL statements and whatnot – it's blocking other writes to the database all that time. This is a direct consequence of how WAL mode operates. Write transactions append changes to the WAL file and they cannot do that in an interleaved manner.

Long write transactions are killers of SQLite concurrency. To avoid them, we need to understand when transactions start and end. This is different for [explicit and implicit transactions](https://www.sqlite.org/lang_transaction.html). Explicit transactions start with `BEGIN` (with a caveat below) and end with `COMMIT` or `ROLLBACK`. If you issue an SQL statement without `BEGIN` first, you'll start an implicit transaction that will end right when the statement finishes. You can think implicit transactions = one statement transactions.

Explicit transactions in turn can be `DEFERRED`, `IMMEDIATE`, or `EXCLUSIVE`. `BEGIN IMMEDIATE` starts a write transaction immediately. So all other writes from `BEGIN IMMEDIATE` until `COMMIT` are blocked. `EXCLUSIVE` works the same way as `IMMEDIATE` in WAL mode.

`BEGIN DEFERRED` works quite differently and it's actually the default – when you issue `BEGIN`, it's `BEGIN DEFERRED`. With `BEGIN DEFERRED`, the transaction does not start immediately. It starts with the first SQL statement. This is the same as for implicit transactions. The difference is that you still need to end the transaction with explicit `COMMIT`.

Read and write transactions are differentiated as follows. `SELECT` statements start read transactions. `INSERT`/`UPDATE`/`DELETE` and other write statements start write transactions. If a read transaction issues a write statement, it's upgraded to a write transaction.

**Note**: SQLite has the [`BEGIN CONCURRENT` extension](https://www.sqlite.org/cgi/src/doc/begin-concurrent/doc/begin_concurrent.md) that implements optimistic locking. A write transaction started with `BEGIN CONCURRENT` does not acquire the write lock until `COMMIT`. If there are no conflicts with other concurrent writes, the transaction succeeds. Otherwise, it fails with an error. `BEGIN CONCURRENT` may increase concurrent write performance, but the application must handle errors appropriately. The extension is part of the SQLite repo, but it lives in a separate branch, and there are no signs it will be merged any time soon.

## Addressing "database is locked" errors

Let's see what happens when transactions compete for the write lock. We start the first write transaction that acquires the lock and does not commit yet:

```
# Transaction 1
sqlite> begin;
sqlite> insert into mytable values('hello!',1);
sqlite> 
```

Now we try to start another write transaction:

```
# Transaction 2
sqlite> begin;
sqlite> insert into mytable values('hello!',2);
Runtime error: database is locked (5)
```

We get a "database is locked" error that is returned immediately on insert! It means having even a small number of concurrent writes is a problem, or your application code should be ready to handle such errors and retry write operations.

The first step to mitigate "database is locked" errors is to set [`PRAGMA busy_timeout`](https://www.sqlite.org/pragma.html#pragma_busy_timeout). It sets the timeout that transactions will wait for the lock before returning "database is locked". For example, setting `PRAGMA busy_timeout=5000;` means transactions will try to acquire the lock for 5 seconds. Note that `busy_timeout` is a connection parameter. You need to set it each time you open an SQLite connection.

What is the optimal `busy_timeout`? SQLite has no recommendations on that. In my benchmarks, anything below 5 seconds led to occasional "database is locked" errors given enough concurrent write transactions, and with 5 seconds and above I didn't notice any errors. You may set it to 10 or 20 seconds. These are some common values in production systems.

A surprising fact for me was that **you can still get "database is locked" errors immediately even after setting `busy_timeout` as if `busy_timeout` has no effect**. This happens when a read transaction upgrades to a write transaction. From the [docs](https://www.sqlite.org/lang_transaction.html):

> If a write statement occurs while a read transaction is active, then the read transaction is upgraded to a write transaction if possible. If some other database connection has already modified the database or is already in the process of modifying the database, then upgrading to a write transaction is not possible and the write statement will fail with [SQLITE_BUSY](https://www.sqlite.org/rescode.html#busy).

The error is returned immediately because it makes no sense to wait. Another transaction already modified the database and possibly invalidated the read, so the write statement is guaranteed to fail. This wouldn't happen if the transaction was started as a write transaction initially because it would have acquired the lock. So one solution to avoid such problems is to start transactions with `BEGIN IMMEDIATE` if they need to write at some point. Another solution is to avoid transactions that perform write-after-read altogether. You probably do that already if you rely on implicit transactions.

Even after you set up an optimal SQLite configuration and optimized transactions, you can still see "database is locked" errors simply because you hit the SQLite performance limits. What are they? How many concurrent writes can SQLite handle? Let's do some benchmarks.

## Benchmarks

First let's try inserting records of different sizes from one thread.
On my MacBook Pro M1 2021, the default SQLite configuration in WAL mode gives the following results:

| Size   | 10B   | 100B  | 1K    | 10K   | 100K | 1MB | 10MB |
| ------ | ----- | ----- | ----- | ----- | ---- | --- | ---- |
| op/sec | 29400 | 29323 | 25906 | 14801 | 3194 | 457 | 43   |

<p style="text-align: center;">size/throughput with default WAL configuration</p>

**Note**: Each insert in performed in a separate transaction since in these benchmarks we're primarily interested in how many concurrent write transactions SQLite can handle. If the goal is max throughput, you'd batch inserts. 

The numbers are ok but they can be improved substantially if we set `PRAGMA synchronous=NORMAL;`:

| Size   | 10B    | 100B   | 1K     | 10K   | 100K  | 1MB   | 10MB  |
|--------|--------|--------|--------|-------|-------|-------|-------|
| op/sec | 103887 | 101338 | 72769  | 24373 | 3994  | 449   | 43    |

<p style="text-align: center;">size/throughput with synchronous=NORMAL</p>

Using this PRAGMA we changed how often SQLite syncs changes to the disk. Default `synchronous=FULL` syncs changes on every commit. `synchronous=NORMAL` syncs changes during checkpointing. It gives away some durability for performance. Committed transactions may roll back following a power loss or system crash but not application crash. This is an acceptable tradeoff for most applications. SQLite recommends setting `synchronous=NORMAL` when using WAL mode. We'll use it for all benchmarks from now on.

So **you can expect SQLite to handle 70k-100k write transactions per second** for typical record sizes. Now let's see what happens when we write in parallel. In this benchmark we insert 1KB records from multiple threads:

| #threads | 1     | 2     | 4     | 8     | 16    | 32    | 64    | 128  | 256   |
| -------- | ----- | ----- | ----- | ----- | ----- | ----- | ----- | ---- | ----- |
| op/sec   | 70301 | 68823 | 66507 | 59485 | 46992 | 41599 | 43793 | 4647 | 12309 |

<p style="text-align: center;">threads/throughput benched for 1s</p>

Note a sudden drop in throughput at 128 threads. This is a [commonly observed](https://www.golang.dk/articles/benchmarking-sqlite-performance-in-go) phenomenon that suggests that SQLite locking may not be very efficient.
However, I observed a different behavior with sufficient benchmark time. When I run the same benchmark 10 times longer, the throughput at 128 is averaged out, but at 256 I get "database is locked":

| #threads | 1     | 2     | 4     | 8     | 16    | 32    | 64    | 128   | 256   |
|----------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| op/sec   | 72016 | 69036 | 71103 | 71908 | 67829 | 67798 | 67764 | 62150 | errors |

<p style="text-align: center;">threads/throughput benched for 10s</p>

In any case the conclusion is that with 100 or more concurrent writers, you'll either get a significant drop in performance or see "database is locked" errors. It doesn't change if they are concurrent but not parallel (e.g. multiple goroutines scheduled on one thread or multiple Python coroutines), the results will be the same.

If SQLite locking cannot coordinate too many concurrent writers, an interesting idea is to replace it with our own app-level lock. All writers would have to acquire the lock before writing to SQLite. In Go code, it would look like this:

```go
var m sync.Mutex

func write(db *sql.DB, content string) error {
	m.Lock()
	defer m.Unlock()
	_, err := db.Exec(`insert into mytable (content) values (?)`, content)
	return err
}
```

Here are the results:

| #threads | 1     | 2     | 4     | 8     | 16    | 32    | 64    | 128   | 256   |
|----------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| op/sec   | 62339 | 66312 | 61746 | 55829 | 61951 | 61626 | 57944 | 59676 | 56770 |

<p style="text-align: center;">threads/throughput with app mutex</p>

What we got is practically the same throughput, but now it stays stable after increasing the number of concurrent writers. There is some overhead but it's negligible. You can go well above 256 and have thousands of them. Moreover, "database is locked" errors are not possible since transactions never fight for the SQLite lock. Magic!

Why is SQLite locking not as good as app-level locking? The short answer is that we used an in-memory lock, and [SQLite uses POSIX advisory locks](https://www.sqlite.org/lockingv3.html) so that the locking mechanism can coordinate different processes.

In most real-world apps, concurrent writes co-exist with reads. But reads do not change our benchmark results much. If some write transactions perform reads, then op/sec would decrease proportionally to the increased transactions duration, so instead of 70k op/sec, you may get 50k op/sec. Only if read transactions totally outnumber write transactions, you could get a different picture due to aforementioned checkpoint starvation. We'll leave its discussion for another time.

## Summary

We now have a recipe for improving SQLite concurrent write performance:

1. Set `PRAGMA journal_mode=WAL;`
2. Set `PRAGMA busy_timeout=5000;` or higher.
3. Set `PRAGMA synchronous=NORMAL;`
4. Keep write transactions small. Ideally, one statement = one transaction.
5. Avoid write-after-read transactions. Use `BEGIN IMMEDIATE` if absolutely necessary.
6. Use app-level locking if you have a lot of concurrent writers.

Most importantly, we now have a good understanding of SQLite limitations. I hope this helps you make better decisions about using SQLite in your systems.

## P.S.

This post was inspired by my work on optimizing [dstack](https://github.com/dstackai/dstack) that uses SQLite as one of its datastores. The benchmarks are adapted from a [post by Markus Wüstenberg](https://www.golang.dk/articles/benchmarking-sqlite-performance-in-go). They're written in Go using [built-in Go benchmarking](https://pkg.go.dev/testing#hdr-Benchmarks) and the [mattn/go-sqlite3](https://github.com/mattn/go-sqlite3) CGO driver. The source code and results are [available in the blog repo](https://github.com/r4victor/tenthousandmeters/tree/master/extras/9922_sqlite_concurrent_writes/go_bench).

Special thanks to Richard Hipp for SQLite and [his lecture on how it works](https://www.youtube.com/watch?v=ZSKLA81tBis).

<br>

*If you have any questions, comments or suggestions, feel free to join the [GitHub discussion](https://github.com/r4victor/tenthousandmeters/discussions/3).*

<br>
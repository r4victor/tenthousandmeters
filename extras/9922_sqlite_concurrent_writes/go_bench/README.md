# SQLite Go benchmarks

The source code and results of SQLite+Go benchmarks for my post SQLite concurrent writes and "database is locked" errors.

The benchmarks are adapted from a [post by Markus Wüstenberg](https://www.golang.dk/articles/benchmarking-sqlite-performance-in-go).

## Results

Note that `synchronous=full` results are not stable. I wouldn't trust the exact numbers but they are certainly worse then ``synchronous=normal`. The `synchronous=normal` results are stable across re-runs.

```
✗ go test -bench BenchmarkWriteDifferentSizes -benchtime=10s -cpu=1
goos: darwin
goarch: arm64
pkg: sqlite_bench
cpu: Apple M1 Pro
BenchmarkWriteDifferentSizes/synchronous=full&size=10b            337362             34012 ns/op
BenchmarkWriteDifferentSizes/synchronous=full&size=100b           335095             34104 ns/op
BenchmarkWriteDifferentSizes/synchronous=full&size=1000b          294226             38602 ns/op
BenchmarkWriteDifferentSizes/synchronous=full&size=10000b         176258             67563 ns/op
BenchmarkWriteDifferentSizes/synchronous=full&size=100000b         39445            313109 ns/op
BenchmarkWriteDifferentSizes/synchronous=full&size=1000000b         5325           2186698 ns/op
BenchmarkWriteDifferentSizes/synchronous=full&size=10000000b         462          23267490 ns/op
BenchmarkWriteDifferentSizes/synchronous=normal&size=10b         1265744              9626 ns/op
BenchmarkWriteDifferentSizes/synchronous=normal&size=100b        1205937              9868 ns/op
BenchmarkWriteDifferentSizes/synchronous=normal&size=1000b        842094             13742 ns/op
BenchmarkWriteDifferentSizes/synchronous=normal&size=10000b       267152             41028 ns/op
BenchmarkWriteDifferentSizes/synchronous=normal&size=100000b       47475            250364 ns/op
BenchmarkWriteDifferentSizes/synchronous=normal&size=1000000b       4587           2224920 ns/op
BenchmarkWriteDifferentSizes/synchronous=normal&size=10000000b       472          23265462 ns/op
PASS
ok      sqlite_bench    202.757s
```

```
✗ go test -bench BenchmarkWriteParallelWithoutMutex -benchtime=1s -cpu=1,2,4,8,16,32,64,128,256 
goos: darwin
goarch: arm64
pkg: sqlite_bench
cpu: Apple M1 Pro
BenchmarkWriteParallelWithoutMutex/synchronous=normal                      83014             14224 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-2                    77092             14530 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-4                    70746             15037 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-8                    72441             16811 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-16                   66392             21280 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-32                   53569             24037 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-64                   46995             22835 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-128                   5066            215185 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-256                  12388             81240 ns/op
PASS
ok      sqlite_bench    21.152s
```

```
✗ go test -bench BenchmarkWriteParallelWithoutMutex -benchtime=10s -cpu=1,2,4,8,16,32,64,128,256
goos: darwin
goarch: arm64
pkg: sqlite_bench
cpu: Apple M1 Pro
BenchmarkWriteParallelWithoutMutex/synchronous=normal                     819127             13887 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-2                   773210             14486 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-4                   851398             14062 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-8                   830948             13906 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-16                  812210             14744 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-32                  821450             14749 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-64                  706692             14758 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-128                 716956             16090 ns/op
BenchmarkWriteParallelWithoutMutex/synchronous=normal-256               --- FAIL: BenchmarkWriteParallelWithoutMutex/synchronous=normal-256
    bench_test.go:122: database is locked
    bench_test.go:122: database is locked
PASS
ok      sqlite_bench    144.310s
```

```
✗ go test -bench BenchmarkWriteConcurrentWithoutMutex -benchtime=10s -cpu=1                     
goos: darwin
goarch: arm64
pkg: sqlite_bench
cpu: Apple M1 Pro
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=1             788043             14264 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=2             766102             14394 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=4             836010             15385 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=8             694596             14626 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=16            801186             14818 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=32            775628             15286 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=64            770797             16020 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=128           711402             16504 ns/op
BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=256         --- FAIL: BenchmarkWriteConcurrentWithoutMutex/synchronous=normal&concurrency=256
    bench_test.go:122: database is locked
    bench_test.go:122: database is locked
    bench_test.go:122: database is locked
--- FAIL: BenchmarkWriteConcurrentWithoutMutex
FAIL
exit status 1
FAIL    sqlite_bench    145.835s
```

```
✗ go test -bench BenchmarkWriteParallelWithMutex -benchtime=10s -cpu=1,2,4,8,16,32,64,128,256
goos: darwin
goarch: arm64
pkg: sqlite_bench
cpu: Apple M1 Pro
BenchmarkWriteParallelWithMutex/synchronous=full                  284138             44529 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-2                295467             63818 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-4                285055            111208 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-8                 66808            193434 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-16                74823            191714 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-32                61168            198539 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-64                51618            266059 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-128              188166            137168 ns/op
BenchmarkWriteParallelWithMutex/synchronous=full-256               56398            229266 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal                865182             16041 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-2              715184             15081 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-4              655700             16196 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-8              609586             17913 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-16             686385             16143 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-32             682774             16227 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-64             656242             17259 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-128            663906             16756 ns/op
BenchmarkWriteParallelWithMutex/synchronous=normal-256            592148             17615 ns/op
PASS
ok      sqlite_bench    328.727s
```

```
✗ go test -bench BenchmarkWriteConcurrentWithMutex -benchtime=10s -cpu=1             
goos: darwin
goarch: arm64
pkg: sqlite_bench
cpu: Apple M1 Pro
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=1                  262087             50069 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=2                  270747             50906 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=4                  281686             48866 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=8                  261302            110752 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=16                 135330            184498 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=32                  61190            268655 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=64                  61467            261047 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=128                 62419            331643 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=full&concurrency=256                 98308            215134 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=1                852265             14464 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=2                730930             16162 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=4                791113             14273 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=8                769484             13514 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=16               797802             14453 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=32               802911             13860 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=64               806990             13863 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=128              777116             14388 ns/op
BenchmarkWriteConcurrentWithMutex/synchronous=normal&concurrency=256              777486             14776 ns/op
PASS
ok      sqlite_bench    305.164s
```

```
✗ go test -bench BenchmarkReadAndWriteConcurrentWithoutMutex -benchtime=10s -cpu=1
goos: darwin
goarch: arm64
pkg: sqlite_bench
cpu: Apple M1 Pro
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=1              621866             17851 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=2              660218             17339 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=4              661756             17957 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=8              620353             19781 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=16             647602             19418 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=32             640682             17757 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=64             594727             17795 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=128            640382             18989 ns/op
BenchmarkReadAndWriteConcurrentWithoutMutex/synchronous=normal&concurrency=256            610244             19626 ns/op
PASS
ok      sqlite_bench    107.599s
```

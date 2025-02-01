// Benchmarks adapted from https://www.golang.dk/articles/benchmarking-sqlite-performance-in-go

package sqlite_bench

import (
	"database/sql"
	"fmt"
	"math"
	"path"
	"strings"
	"sync"
	"testing"

	_ "github.com/mattn/go-sqlite3"
)

func BenchmarkWriteDifferentSizes(b *testing.B) {
	for _, sync := range []string{"full", "normal"} {
		for pow := 1; pow <= 7; pow++ {
			size := int(math.Pow(10, float64(pow)))
			b.Run(fmt.Sprintf("synchronous=%s&size=%db", sync, size), func(b *testing.B) {
				options := fmt.Sprintf("?_journal=WAL&_timeout=5000&_fk=true&_synchronous=%s", sync)
				db := makeDB(b, options)
				content := strings.Repeat("A", size)

				b.ResetTimer()
				for i := 0; i < b.N; i++ {
					err := writeBlogPost(db, content)
					noErr(b, err)
				}
			})
		}
	}
}

// BenchmarkWriteConcurrentWithoutMutex runs n goroutines in one thread.
// Should be used with -cpu=1.
func BenchmarkWriteConcurrentWithoutMutex(b *testing.B) {
	// with enough benchtime, _synchronous=full gives database is locked
	// even for _timeoute>10000, so not benchmarking it without mutex
	for _, sync := range []string{"normal"} {
		for _, concurrency := range []int{1, 2, 4, 8, 16, 32, 64, 128, 256} {
			b.Run(fmt.Sprintf("synchronous=%s&concurrency=%d", sync, concurrency), func(b *testing.B) {
				options := fmt.Sprintf("?_journal=WAL&_timeout=5000&_fk=true&_synchronous=%s", sync)
				db := makeDB(b, options)
				content := strings.Repeat("A", 1000)
				b.SetParallelism(concurrency)
				b.ResetTimer()
				b.RunParallel(func(pb *testing.PB) {
					for pb.Next() {
						err := writeBlogPost(db, content)
						noErr(b, err)
					}
				})
			})
		}
	}
}

// BenchmarkWriteParallelWithoutMutex runs -cpu goroutines in -cpu threads.
// Should be used with -cpu=1,2,4,8,16,32,64,128,256.
func BenchmarkWriteParallelWithoutMutex(b *testing.B) {
	// with enough benchtime, _synchronous=full gives database is locked
	// even for _timeoute>10000, so not benchmarking it without mutex
	for _, sync := range []string{"normal"} {
		b.Run(fmt.Sprintf("synchronous=%s", sync), func(b *testing.B) {
			options := fmt.Sprintf("?_journal=WAL&_timeout=5000&_fk=true&_synchronous=%s", sync)
			db := makeDB(b, options)
			content := strings.Repeat("A", 1000)
			b.ResetTimer()
			b.RunParallel(func(pb *testing.PB) {
				for pb.Next() {
					err := writeBlogPost(db, content)
					noErr(b, err)
				}
			})
		})
	}
}

func BenchmarkWriteConcurrentWithMutex(b *testing.B) {
	for _, sync := range []string{"full", "normal"} {
		for _, concurrency := range []int{1, 2, 4, 8, 16, 32, 64, 128, 1024} {
			b.Run(fmt.Sprintf("synchronous=%s&concurrency=%d", sync, concurrency), func(b *testing.B) {
				options := fmt.Sprintf("?_journal=WAL&_timeout=5000&_fk=true&_synchronous=%s", sync)
				db := makeDB(b, options)
				content := strings.Repeat("A", 1000)
				b.SetParallelism(concurrency)
				b.ResetTimer()
				b.RunParallel(func(pb *testing.PB) {
					for pb.Next() {
						err := writeBlogPostMutexed(db, content)
						noErr(b, err)
					}
				})
			})
		}
	}
}

// BenchmarkWriteParallelWithMutex runs -cpu goroutines in -cpu threads.
// Should be used with -cpu=1,2,4,8,16,32,64,128,256.
func BenchmarkWriteParallelWithMutex(b *testing.B) {
	for _, sync := range []string{"full", "normal"} {
		b.Run(fmt.Sprintf("synchronous=%s", sync), func(b *testing.B) {
			options := fmt.Sprintf("?_journal=WAL&_timeout=5000&_fk=true&_synchronous=%s", sync)
			db := makeDB(b, options)
			content := strings.Repeat("A", 1000)
			b.ResetTimer()
			b.RunParallel(func(pb *testing.PB) {
				for pb.Next() {
					err := writeBlogPostMutexed(db, content)
					noErr(b, err)
				}
			})
		})
	}
}

func BenchmarkReadAndWriteConcurrentWithoutMutex(b *testing.B) {
	for _, sync := range []string{"normal"} {
		for _, concurrency := range []int{1, 2, 4, 8, 16, 32, 64, 128, 256} {
			b.Run(fmt.Sprintf("synchronous=%s&concurrency=%d", sync, concurrency), func(b *testing.B) {
				options := fmt.Sprintf("?_journal=WAL&_timeout=5000&_fk=true&_synchronous=%s", sync)
				db := makeDB(b, options)
				content := strings.Repeat("A", 1000)
				b.SetParallelism(concurrency)
				b.ResetTimer()
				b.RunParallel(func(pb *testing.PB) {
					for pb.Next() {
						err := readBlogPost(db)
						noErr(b, err)
						err = writeBlogPostMutexed(db, content)
						noErr(b, err)
					}
				})
			})
		}
	}
}

func noErr(b *testing.B, err error) {
	if err != nil {
		b.Fatal(err)
	}
}

func makeDB(b *testing.B, options string) *sql.DB {
	dbPath := path.Join(b.TempDir(), "benchmark.db")
	db, err := sql.Open("sqlite3", dbPath+options)
	if err != nil {
		b.Fatal(err)
	}
	if err := setupDB(db); err != nil {
		b.Fatal(err)
	}
	return db
}

func setupDB(db *sql.DB) error {
	_, err := db.Exec(`
			create table posts (
				id integer primary key,
				content text not null
			)`)
	return err
}

func writeBlogPost(db *sql.DB, content string) error {
	_, err := db.Exec(`insert into posts (content) values (?)`, content)
	return err
}

var m sync.Mutex

func writeBlogPostMutexed(db *sql.DB, content string) error {
	m.Lock()
	defer m.Unlock()
	_, err := db.Exec(`insert into posts (content) values (?)`, content)
	return err
}

func readBlogPost(db *sql.DB) error {
	_, err := db.Exec(`select * from posts limit 1`)
	return err
}

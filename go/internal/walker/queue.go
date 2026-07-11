package walker

import "sync"

// taskQueue is an unbounded work queue of directories.
//
// A fixed-size channel cannot be used here: every directory task can
// enqueue arbitrarily many subdirectory tasks, so with a bounded channel a
// full complement of blocked producers deadlocks on deep or wide trees.
// This queue grows a slice under a mutex instead; workers block on a
// condition variable and drain until the queue is empty *and* no task is
// still in flight (an in-flight task may yet push more work).
type taskQueue struct {
	mu          sync.Mutex
	cond        *sync.Cond
	tasks       []dirTask
	outstanding int // tasks pushed but not yet done()
}

func newTaskQueue() *taskQueue {
	q := &taskQueue{}
	q.cond = sync.NewCond(&q.mu)
	return q
}

// push adds a task. The caller must eventually call done() once for every
// pushed task, after the task has been fully processed (including pushing
// any child tasks).
func (q *taskQueue) push(t dirTask) {
	q.mu.Lock()
	q.tasks = append(q.tasks, t)
	q.outstanding++
	q.mu.Unlock()
	q.cond.Signal()
}

// pop blocks until a task is available or the walk is complete.
// It returns ok=false when no tasks remain and none are in flight.
func (q *taskQueue) pop() (t dirTask, ok bool) {
	q.mu.Lock()
	defer q.mu.Unlock()
	for len(q.tasks) == 0 && q.outstanding > 0 {
		q.cond.Wait()
	}
	if len(q.tasks) == 0 {
		return dirTask{}, false
	}
	// LIFO order keeps the queue small (depth-first-ish) on huge trees.
	t = q.tasks[len(q.tasks)-1]
	q.tasks = q.tasks[:len(q.tasks)-1]
	return t, true
}

// done marks one previously popped task as fully processed. When the last
// in-flight task completes with the queue empty, all blocked poppers wake
// up and return ok=false.
func (q *taskQueue) done() {
	q.mu.Lock()
	q.outstanding--
	finished := q.outstanding == 0
	q.mu.Unlock()
	if finished {
		q.cond.Broadcast()
	}
}

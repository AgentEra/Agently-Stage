// Synthetic arithmetic/FFI probe, not a Stage replacement.
package main

import "C"

//export kernel
func kernel(seed C.ulonglong, iterations C.ulonglong) C.ulonglong {
    x := uint64(seed) + 1
    for i := uint64(0); i < uint64(iterations); i++ {
        x = (x ^ (x >> 7)) * 6364136223846793005 + 1
    }
    return C.ulonglong(x)
}

//export batch
func batch(count C.ulonglong, iterations C.ulonglong) C.ulonglong {
    var sum uint64
    for i := uint64(0); i < uint64(count); i++ {
        sum += uint64(kernel(C.ulonglong(i), iterations))
    }
    return C.ulonglong(sum)
}

func main() {}

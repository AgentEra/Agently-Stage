// Synthetic arithmetic/FFI probe, not a Stage replacement.
#[unsafe(no_mangle)]
pub extern "C" fn kernel(seed: u64, iterations: u64) -> u64 {
    let mut x = seed.wrapping_add(1);
    for _ in 0..iterations {
        x = (x ^ (x >> 7)).wrapping_mul(6364136223846793005).wrapping_add(1);
    }
    x
}

#[unsafe(no_mangle)]
pub extern "C" fn batch(count: u64, iterations: u64) -> u64 {
    (0..count).fold(0u64, |sum, i| sum.wrapping_add(kernel(i, iterations)))
}

#[unsafe(no_mangle)]
pub extern "C" fn callbacks(callback: extern "C" fn(u64) -> u64, count: u64, workers: u64) -> u64 {
    let handles: Vec<_> = (0..workers).map(|worker| std::thread::spawn(move || {
        (worker..count).step_by(workers as usize)
            .fold(0u64, |sum, i| sum.wrapping_add(callback(i)))
    })).collect();
    handles.into_iter().fold(0u64, |sum, h| sum.wrapping_add(h.join().unwrap()))
}

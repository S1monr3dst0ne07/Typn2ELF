# Typn2ELF

This is a flat, single-pass compiler for the [Typn](https://github.com/TheGameGuy2/Typn-Language) programming language.
Implementation is incomplete, but provided example programs run. The benchmark present in the Typn source repo is
also prevent and can be run with `make bench`.

### Benchmark Result
These are from my machine, but should be relatively proportionate.
The compiled binary from this compiler is about half as fast
as the one from GCC with `-O0`.
```
--- python version ---
100000000

real    0m10.792s
user    0m10.780s
sys     0m0.012s
--- c version ---
100000000
real    0m0.235s
user    0m0.235s
sys     0m0.000s
--- compiled version ---
100000000

real    0m0.458s
user    0m0.457s
sys     0m0.000s
```



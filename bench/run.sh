#!/usr/bin/bash

echo "--- python version ---"
time python3 prog.py

echo "--- c version ---"
gcc -O0 prog.c
time ./a.out
rm a.out

echo "--- compiled version ---"
../compile.py prog.tpy
chmod +x a.out
time ./a.out
rm a.out



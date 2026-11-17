.PHONY: run bench

run:
	./compile.py examples/mandel.tpy
	chmod +x a.out
	./a.out

bench:
	cd bench; ./run.sh

disasm:
	dd if=a.out of=a.bin bs=1 skip=120
	objdump -D -b binary -m i386:x86-64 -M intel a.bin

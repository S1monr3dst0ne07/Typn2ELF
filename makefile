.PHONY: run bench

run:
	./compile.py examples/main.tpy
	chmod +x a.out
	./a.out

bench:
	cd bench; ./run.sh



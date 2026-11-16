#!/usr/bin/python3
import sys
from dataclasses import dataclass as dc

def tokenize(path):
	with open(path, 'r') as f:
		src = f.read()

	def get(char):
		match char:
			case ' ' | '\t' | '\n': return 'format'
			case x if x.isalnum() : return 'iden'
			case '': return None
			case _: return 'symbol'

	tokens = []
	buffer = ''

	state_multi_comment  = False
	state_single_comment = False

	last_char  = ''
	for char in src:
		buffer += last_char

		last_state = get(last_char)
		last_char  = char

		if not last_state: continue
		if     last_state == get(char): continue
	
		if buffer == '//' : state_single_comment = True
		if buffer == '###' and not state_multi_comment:
			state_multi_comment = True
			buffer = ''

		not_comment = (not state_multi_comment) and (not state_single_comment)
		if last_state != 'format' and not_comment:
			tokens.append(buffer)

		if char   == '\n': state_single_comment = False
		if buffer == '###' and state_multi_comment:
			state_multi_comment = False

		buffer = ''

	@dc
	class Streamer:
		token : list[str]
		index : int = 0

		def peek(self):
			return self.token[self.index]
		def pop(self):
			tok = self.peek()
			self.index += 1
			return tok
		def expect(self, iden):
			tok = self.pop()
			if tok != iden:
				import traceback; traceback.print_stack()
				print(f"Error: Expcted `{iden}` got `{tok}`")
				sys.exit(1)
		def has(self):
			return self.index < len(self.token)
			

	return Streamer(tokens)

LOAD_ADDR = 0x400000
HEADER_SIZE = 120
TYPE_IDEN = ('int', 'bool')
OPERS = ('+', '-', '*', '/', '&&', '||', '<', '>')

vars = {}
output = []

def emitn(value, n): 
	for i in range(n):
		output.append((value >> (i*8)) & 255)
def emit8(x) : emitn(x, 1)
def emit16(x): emitn(x, 2)
def emit32(x): emitn(x, 4)
def emit64(x): emitn(x, 8)

def patchn(addr, value, n):
	for i in range(n):
		output[i+addr] = ((value >> (i*8)) & 255)
def patch32(addr, x): patchn(addr, x, 4)

def addr(): return len(output)

@dc
class Var:
	type_iden : str
	name      : str
	offset    : int

def compile_var_store(var):
	# mov [rbp + offset*8], rax
	emit8(0x48)
	emit8(0x89)
	emit8(0b10000101)
	emit32(var.offset * 8)
def compile_var_load(var):
	# mov rax, [rbp + offset*8]
	emit8(0x48)
	emit8(0x8b)
	emit8(0b10000101)
	emit32(var.offset * 8)

def compile_leaf(stream):
	match stream.pop():
		case x if x.isdigit():
			# mov rax, imm64
			emit8(0x48)
			emit8(0xb8)
			emit64(int(x))
		case x if x in vars:
			compile_var_load(vars[x])
		case '(':
			compile_expr(stream)
			stream.expect(')')
		case x:
			print(f"Expected leaf got `{x}`")

def compile_unary(stream):
	compile_leaf(stream)

def compile_expr(stream):
	compile_unary(stream)

	if stream.peek() not in OPERS:
		return
	
	op = stream.pop()

	emit8(0x50) # push rax
	compile_unary(stream)
	emit8(0x59) # pop rbx

	def compile_compare(op):
		# cmp rax, rbx
		# setOP cl
		# movzx rax, cl
		emit8(0x48)
		emit8(0x39)
		emit8(0xd8)

		emit8(0x0f)
		emit8(op)
		emit8(0xc1)

		emit8(0x48)
		emit8(0x0f)
		emit8(0xb6)
		emit8(0xc1)


	match op:
		case '<': compile_compare(0x92)
		case '>': compile_compare(0x97)

		case '+':
			emit8(0x48)
			emit8(0x01)
			emit8(0b11001000)
		case '-':
			emit8(0x48)
			emit8(0x29)
			emit8(0b11001000)
		
		


def compile_var_decl(stream):
	type_iden = stream.pop()
	stream.expect(':')
	name = stream.pop()

	var = Var(type_iden, name, len(vars))
	vars[name] = var

	match stream.pop():
		case ';': pass
		case '=':
			compile_expr(stream)
			compile_var_store(var)
		case x:
			print(f"Error: Unexpected symbol `{x}` terminating variable declaration")
			sys.exit(1)

def compile_while(stream):
	stream.expect('while')

	loop_addr = addr()
	compile_expr(stream) # condition
	# test al, 1
	# jz done
	emit8(0xa8)
	emit8(0x01)
	emit8(0x0f)
	emit8(0x84)
	done_patch = addr()
	emit32(0)

	compile_block(stream)

	# jmp loop
	emit8(0xe9)
	emit32(loop_addr - addr() - 4)

	# back jz done
	patch32(done_patch, addr() - done_patch - 4)

def compile_assign(name, stream):
	stream.expect('=')
	compile_expr(stream)
	compile_var_store(vars[name])

def compile_call(name, stream):
	stream.expect('(')
	compile_expr(stream)
	stream.expect(')')

def compile_stmt(stream):
	match stream.peek():
		case x if x in TYPE_IDEN: compile_var_decl(stream)
		case 'while':             compile_while(stream)

		case x if x.isalpha():
			name = stream.pop()
			match stream.peek():
				case '=': compile_assign(name, stream)
				case '(': compile_call  (name, stream)

			

def compile_block(stream, brackets=True):
	if brackets: stream.expect('{')

	while True:
		if not stream.has(): break
		if brackets and stream.peek() == '}': break

		compile_stmt(stream)

	if brackets: stream.expect('}')


def main():
	stream = tokenize(sys.argv[1])
	compile_block(stream, brackets=False)

	# mov rax, 60
	# mov rdi, 0
	# syscall
	emit8(0x48); emit8(0xc7); emit8(0xc0); emit32(60)
	emit8(0x48); emit8(0xc7); emit8(0xc7); emit32(0)
	emit8(0x0f); emit8(0x05)

	with open('a.out', 'wb') as f:
		f.write(bytes(output))

if __name__ == "__main__":
	main()



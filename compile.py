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
			case '(' | ')'        : return 'paren'
			case '_'              : return 'iden'
			case ''               : return  None
			case _                : return 'symbol'

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
		if     last_state == get(char) and last_state != 'paren': continue
	
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
OPERS = ('+', '-', '*', '/', '&&', '||', '<', '>', '==', '<=', '>=')

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
def patch64(addr, x): patchn(addr, x, 8)

def addr(): return len(output)

@dc
class Var:
	type_iden : str
	name      : str
	offset    : int
	scope     : int = 0

# this scope-depth tracking system is horrible,
# but it should be simple and should work...
def enter_scope():
	for var in vars.values(): var.scope += 1
def leave_scope():
	dead_names = set()
	for name, var in vars.items(): 
		var.scope -= 1
		if var.scope < 0: dead_names.add(name)
	for dead_name in dead_names:
		del vars[dead_name]

def var_lookup(name):
	if name not in vars:
		print(f"Error: Trying to access undefined variable `{name}`.")
		sys.exit(1)

	return vars[name]

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
			# MOV rax, imm64
			emit8(0x48); emit8(0xb8); emit64(int(x))
		case '(':
			compile_expr(stream)
			stream.expect(')')
		case 'true' : emit8(0x48); emit8(0xb8); emit64(1) # MOV rax, 1
		case 'false': emit8(0x48); emit8(0xb8); emit64(0) # MOV rax, 0

		case name:
			compile_var_load(var_lookup(name))

def compile_unary(stream):
	compile_leaf(stream)

def compile_compare(op):
	# CMP   rax, rcx
	# SETCC cl
	# MOVZX rax, cl
	emit8(0x48); emit8(0x39); emit8(0xc8)
	emit8(0x0f); emit8(op)  ; emit8(0xc1)
	emit8(0x48); emit8(0x0f); emit8(0xb6); emit8(0xc1)

def compile_first_order(op):
	emit8(0x48)
	emit8(op)
	emit8(0b11001000)

def compile_expr(stream):
	compile_unary(stream)

	if stream.peek() not in OPERS:
		return
	
	op = stream.pop()

	emit8(0x50) # push rax
	compile_unary(stream)
	emit8(0x59) # pop rbx

	match op:
		case '>':  compile_compare(0x9c) # less
		case '<':  compile_compare(0x9f) # greater
		case '>=': compile_compare(0x9e) # less equal
		case '<=': compile_compare(0x9d) # greater equal
		case '==': compile_compare(0x94) # equal

		case '&&': compile_first_order(0x21)
		case '||': compile_first_order(0x09)

		case '+': compile_first_order(0x01)
		case '-': compile_first_order(0x29)

		case x:
			print(f"Expected operator got `{x}`")
			sys.exit(1)

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
	# TEST al, 1
	# JZ   <placeholder>
	emit8(0xa8); emit8(0x01); emit8(0x0f); 
	done_patch = addr() + 1; 
	emit8(0x84); emit32(0)

	compile_block(stream)

	# JMP loop
	emit8(0xe9)
	emit32(loop_addr - addr() - 4)

	# JZ done
	patch32(done_patch, addr() - done_patch - 4)

def compile_if(stream):
	stream.expect('if')

	compile_expr(stream) # condition
	# TEST al, 1
	# JZ   <placeholder>
	emit8(0xa8); emit8(0x01); emit8(0x0f); 
	patch = addr() + 1; 
	emit8(0x84); emit32(0)

	compile_block(stream)

	# JZ skip
	patch32(patch, addr() - patch - 4)


def compile_assign(name, stream):
	stream.expect('=')
	compile_expr(stream)
	compile_var_store(var_lookup(name))

def compile_call(name, stream):
	stream.expect('(')
	compile_expr(stream)
	stream.expect(')')

	match name:
		case 'print':
			blob = [
				0x4c, 0x8d, 0x4c, 0x24, 0xfe,             #  0:   4c 8d 4c 24 fe          lea    r9,[rsp-0x2]
				0x4d, 0x31, 0xd2,                         #  5:   4d 31 d2                xor    r10,r10
				0x41, 0xc6, 0x41, 0x01, 0x0a,             #  8:   41 c6 41 01 0a          mov    BYTE PTR [r9+0x1],0xa
				0x41, 0xc6, 0x01, 0x30,                   #  d:   41 c6 01 30             mov    BYTE PTR [r9],0x30
				0x49, 0xc7, 0xc0, 0x0a, 0x00, 0x00, 0x00, # 11:   49 c7 c0 0a 00 00 00    mov    r8,0xa
				0x48, 0x85, 0xc0,                         # 18:   48 85 c0                test   rax,rax
				0x74, 0x14,                               # 1b:   74 14                   je     0x31
				0x48, 0x31, 0xd2,                         # 1d:   48 31 d2                xor    rdx,rdx
				0x49, 0xf7, 0xf0,                         # 20:   49 f7 f0                div    r8
				0x80, 0xc2, 0x30,                         # 23:   80 c2 30                add    dl,0x30
				0x41, 0x88, 0x11,                         # 26:   41 88 11                mov    BYTE PTR [r9],dl
				0x49, 0xff, 0xc2,                         # 29:   49 ff c2                inc    r10
				0x49, 0xff, 0xc9,                         # 2c:   49 ff c9                dec    r9
				0xeb, 0xe7,                               # 2f:   eb e7                   jmp    0x18
				0x48, 0xc7, 0xc0, 0x01, 0x00, 0x00, 0x00, # 31:   48 c7 c0 01 00 00 00    mov    rax,0x1
				0x48, 0xc7, 0xc7, 0x01, 0x00, 0x00, 0x00, # 38:   48 c7 c7 01 00 00 00    mov    rdi,0x1
				0x4c, 0x89, 0xce,                         # 3f:   4c 89 ce                mov    rsi,r9
				0x49, 0x8d, 0x52, 0x2,                    # 42:   49 8d 52 02             lea    rdx,[r10+0x2]
				0x0f, 0x05,                               # 46:   0f 05                   syscall

			]

			output.extend(blob)

def compile_first_order_inplace(name, stream, op):
	compile_expr(stream)

	emit8(0x50) # push rax
	compile_var_load(var_lookup(name))
	emit8(0x59) # pop rbx

	compile_first_order(op)

	compile_var_store(var_lookup(name))

def compile_inplace_add(name, stream):
	stream.expect('+=')
	compile_first_order_inplace(name, stream, 0x01)


def compile_inplace_sub(name, stream):
	stream.expect('-=')
	compile_first_order_inplace(name, stream, 0x29)

def compile_stmt(stream):
	match stream.peek():
		case x if x in TYPE_IDEN: compile_var_decl(stream)
		case 'while':             compile_while   (stream)
		case 'if'   :             compile_if      (stream)

		case x if x.isalpha():
			name = stream.pop()
			match stream.peek():
				case '=' : compile_assign     (name, stream)
				case '(' : compile_call       (name, stream)

				# not the spec grammar, but example use it anyhow
				case '+=': compile_inplace_add(name, stream)
				case '-=': compile_inplace_sub(name, stream)

				case x:
					print(f"Expected variable expression got `{x}`")

		case x:
			print(f"Expected expression got `{x}`")


def compile_block(stream, brackets=True):
	enter_scope()
	if brackets: stream.expect('{')

	while True:
		if not stream.has(): break
		if brackets and stream.peek() == '}': break

		compile_stmt(stream)

	if brackets: stream.expect('}')
	leave_scope()


def emit_elf_headers():
	emit8(0x7f); emit8(0x45); emit8(0x4c); emit8(0x46) # EI_MAG
	emit8(2)     # EI_CLASS   = 64 bit
	emit8(1)     # EI_DATA    = LE
	emit8(1)     # EI_VERSION = version one
	emit8(0)     # EI_OSABI   = System V
	emit8(0)     # EI_ABIVERSIOn = 0
	emitn(0, 7)  # EI_PAD

	emit16(2)                       # e_type = ET_EXEC
	emit16(0x3e)                    # e_machine = AMD64
	emit32(1)                       # e_version
	emit64(LOAD_ADDR + HEADER_SIZE) # e_entry 
	emit64(0x40) # e_phoff
	emit64(0x00) # e_shoff
	emit32(0)    # e_flags
	emit16(64)   # e_ehsize
	emit16(0x38) # e_phentsize
	emit16(1)    # e_phnum
	emit16(0)    # e_shentsize
	emit16(0)    # e_shnum
	emit16(0)    # e_shstrndx

	emit32(1          ) # p_type = PT_LOAD
	emit32(0b111      ) # p_flags = RWX
	emit64(0          ) # p_offset
	emit64(LOAD_ADDR  ) # p_vaddr
	emit64(LOAD_ADDR  ) # p_paddr

	file_size_patch = addr()
	emit64(0          ) # p_filesz = <placeholder>
	emit64(0x100000   ) # p_memsz = 1M
	emit64(0x1000     ) # p_align

	return file_size_patch

def emit_rbp_init():
	emit8(0x48)
	emit8(0xc7)
	emit8(0xc5)
	rbp_init_patch = addr()
	emit32(0)

	return rbp_init_patch

def main():
	stream = tokenize(sys.argv[1])
	file_size_patch = emit_elf_headers()
	rbp_init_patch  = emit_rbp_init()

	compile_block(stream, brackets=False)

	# mov rax, 60
	# mov rdi, 0
	# syscall
	emit8(0x48); emit8(0xc7); emit8(0xc0); emit32(60)
	emit8(0x48); emit8(0xc7); emit8(0xc7); emit32(0)
	emit8(0x0f); emit8(0x05)

	patch64(file_size_patch, len(output))
	patch32(rbp_init_patch,  len(output) + LOAD_ADDR)

	with open('a.out', 'wb') as f:
		f.write(bytes(output))

if __name__ == "__main__":
	main()



#!/usr/bin/python3
import sys


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

	return tokens



def main():
	stream = tokenize(sys.argv[1])
	print(stream)


if __name__ == "__main__":
	main()



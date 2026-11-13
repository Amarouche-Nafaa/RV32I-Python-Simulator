# assembler.py
import re
from riscv_defs import *

def parse_register(reg_str):
    reg_str = reg_str.strip().lower()
    if reg_str in ABI_TO_INDEX:
        return ABI_TO_INDEX[reg_str]
    elif reg_str.startswith('x') and reg_str[1:].isdigit():
        idx = int(reg_str[1:])
        if 0 <= idx < 32:
            return idx
    raise ValueError(f"Invalid register name: '{reg_str}'")

def _normalize_li_imm(imm_str):
    imm = int(imm_str, 0)
    if 0x80000000 <= imm <= 0xFFFFFFFF:
        imm -= 0x100000000
    if not (-0x80000000 <= imm <= 0x7FFFFFFF):
        raise ValueError(f"Immediate '{imm_str}' out of 32-bit range for 'li'.")
    return imm

def _expand_li(rd_str, imm):
    if I_TYPE_IMM_MIN <= imm <= I_TYPE_IMM_MAX:
        return [('addi', [rd_str, 'zero', str(imm)])]
    upper = ((imm + 0x800) >> 12) & 0xFFFFF
    lower = imm & 0xFFF
    if lower & 0x800:
        lower -= 0x1000
    instrs = [('lui', [rd_str, str(upper)])]
    if lower != 0:
        instrs.append(('addi', [rd_str, rd_str, str(lower)]))
    else:
        # Keep 2-instruction expansion consistent with Pass 1 address calculation and UI logs
        instrs.append(('addi', [rd_str, rd_str, '0']))
    return instrs

def parse_assembly(assembly_text):
    raw_lines = [line.split('#')[0].strip().lower() for line in assembly_text.strip().split('\n')]

    # Normalize lines so inline labels like "loop: addi t0, t0, 1" work seamlessly
    source_lines = []
    for line_num, raw_line in enumerate(raw_lines, start=1):
        if not raw_line:
            continue
        while ':' in raw_line:
            label_part, rest = raw_line.split(':', 1)
            label_name = label_part.strip()
            if not re.match(r'^[a-z_][a-z0-9_]*$', label_name):
                raise ValueError(f"Line {line_num}: Invalid label name '{label_name}'.")
            source_lines.append((line_num, f"{label_name}:"))
            raw_line = rest.strip()
        if raw_line:
            source_lines.append((line_num, raw_line))

    # --- PASS 1: Build Symbol Table ---
    symbol_table, current_address = {}, 0
    for line_num, line in source_lines:
        if line.endswith(':'):
            label_name = line[:-1]
            if label_name in symbol_table:
                raise ValueError(f"Line {line_num}: Duplicate label '{label_name}'.")
            symbol_table[label_name] = current_address
        else:
            parts = re.split(r'\s+', line.replace(',', ' ').strip())
            op = parts[0]
            if op == 'li':
                if len(parts) != 3:
                    raise ValueError(f"Line {line_num}: 'li' expects 2 arguments (rd, imm), got: '{line}'")
                imm_val = _normalize_li_imm(parts[2])
                if not (I_TYPE_IMM_MIN <= imm_val <= I_TYPE_IMM_MAX):
                    current_address += 4
            current_address += 4

    # --- PASS 2: Encode Instructions ---
    machine_code, disassembly, expansion_log = [], {}, []
    current_address = 0
    for line_num, line in source_lines:
        if line.endswith(':'):
            continue
        original_line = line
        parts = re.split(r'\s+', line.replace(',', ' ').strip())
        op = parts[0]

        # Handle Pseudo-Instructions
        if op == 'j':
            if len(parts) != 2:
                raise ValueError(f"Line {line_num}: 'j' expects 1 argument (label).")
            expansion_log.append(f"L{line_num}: `j {parts[1]}` -> `jal zero, {parts[1]}`")
            parts = ['jal', 'zero', parts[1]]
        elif op == 'jr':
            if len(parts) != 2:
                raise ValueError(f"Line {line_num}: 'jr' expects 1 argument (rs1).")
            expansion_log.append(f"L{line_num}: `jr {parts[1]}` -> `jalr zero, {parts[1]}, 0`")
            parts = ['jalr', 'zero', parts[1], '0']
        elif op == 'mv':
            if len(parts) != 3:
                raise ValueError(f"Line {line_num}: 'mv' expects 2 arguments (rd, rs1).")
            expansion_log.append(f"L{line_num}: `mv {parts[1]}, {parts[2]}` -> `addi {parts[1]}, {parts[2]}, 0`")
            parts = ['addi', parts[1], parts[2], '0']
        elif op == 'nop':
            if len(parts) != 1:
                raise ValueError(f"Line {line_num}: 'nop' takes no arguments.")
            expansion_log.append(f"L{line_num}: `nop` -> `addi zero, zero, 0`")
            parts = ['addi', 'zero', 'zero', '0']
        elif op == 'ret':
            if len(parts) != 1:
                raise ValueError(f"Line {line_num}: 'ret' takes no arguments.")
            expansion_log.append(f"L{line_num}: `ret` -> `jalr zero, ra, 0`")
            parts = ['jalr', 'zero', 'ra', '0']
        op = parts[0]

        instr_list = []
        if op == 'li':
            rd_str = parts[1]
            imm = _normalize_li_imm(parts[2])
            expanded = _expand_li(rd_str, imm)
            instr_list.extend(expanded)
            if len(expanded) == 1:
                expansion_log.append(f"L{line_num}: `{original_line}` -> `addi {rd_str}, zero, {imm}`")
            else:
                upper_str = expanded[0][1][1]
                lower_str = expanded[1][1][2]
                expansion_log.append(
                    f"L{line_num}: `{original_line}` -> `lui {rd_str}, {hex(int(upper_str))}`; `addi {rd_str}, {rd_str}, {lower_str}`"
                )
        else:
            instr_list.append((op, parts[1:]))

        # Encode the instruction(s)
        for instr_name, args in instr_list:
            mc = None
            # --- ENCODING LOGIC ---
            if instr_name in ['add', 'sub', 'sll', 'slt', 'sltu', 'xor', 'srl', 'sra', 'or', 'and']:
                if len(args) != 3:
                    raise ValueError(f"Line {line_num}: '{instr_name}' expects 3 arguments (rd, rs1, rs2).")
                rd, rs1, rs2 = parse_register(args[0]), parse_register(args[1]), parse_register(args[2])
                funct3_map = {
                    'add': F3_ADD_SUB, 'sub': F3_ADD_SUB, 'sll': F3_SLL, 'slt': F3_SLT, 'sltu': F3_SLTU,
                    'xor': F3_XOR, 'srl': F3_SRL_SRA, 'sra': F3_SRL_SRA, 'or': F3_OR, 'and': F3_AND
                }
                funct7_map = {'add': F7_ADD, 'sub': F7_SUB, 'srl': F7_SRL, 'sra': F7_SRA}
                mc = encode_r(funct7_map.get(instr_name, F7_ADD), rs2, rs1, funct3_map[instr_name], rd, OPCODE_REG)

            elif instr_name in ['addi', 'slti', 'sltiu', 'xori', 'ori', 'andi', 'slli', 'srli', 'srai', 'jalr']:
                if instr_name == 'jalr' and len(args) == 2:
                    # Support jalr rd, imm(rs1) syntax as well as jalr rd, rs1, imm
                    rd = parse_register(args[0])
                    mem_op = re.match(r'^(-?(?:0x[0-9a-f]+|\d+))\((\w+)\)$', args[1])
                    if not mem_op:
                        raise ValueError(f"Line {line_num}: Invalid memory operand '{args[1]}' for jalr.")
                    imm, rs1 = int(mem_op.group(1), 0), parse_register(mem_op.group(2))
                else:
                    if len(args) != 3:
                        raise ValueError(f"Line {line_num}: '{instr_name}' expects 3 arguments.")
                    rd, rs1, imm = parse_register(args[0]), parse_register(args[1]), int(args[2], 0)

                opcode = OPCODE_JALR if instr_name == 'jalr' else OPCODE_IMM
                funct3_map = {
                    'addi': F3_ADD_SUB, 'slti': F3_SLT, 'sltiu': F3_SLTU, 'xori': F3_XOR,
                    'ori': F3_OR, 'andi': F3_AND, 'slli': F3_SLL, 'srli': F3_SRL_SRA,
                    'srai': F3_SRL_SRA, 'jalr': F3_ADD_SUB
                }
                if instr_name in ['slli', 'srli', 'srai']:
                    check_imm(imm, SHAMT_MIN, SHAMT_MAX, instr_name)
                    mc = encode_r(F7_SRA if instr_name == 'srai' else F7_SRL, imm, rs1, funct3_map[instr_name], rd, OPCODE_IMM)
                else:
                    check_imm(imm, I_TYPE_IMM_MIN, I_TYPE_IMM_MAX, instr_name)
                    mc = encode_i(imm, rs1, funct3_map[instr_name], rd, opcode)

            elif instr_name in ['lui', 'auipc']:
                if len(args) != 2:
                    raise ValueError(f"Line {line_num}: '{instr_name}' expects 2 arguments (rd, imm).")
                rd, imm = parse_register(args[0]), int(args[1], 0)
                check_imm(imm, U_IMM_MIN, U_IMM_MAX, instr_name)
                opcode = OPCODE_AUIPC if instr_name == 'auipc' else OPCODE_LUI
                mc = encode_u(imm, rd, opcode)

            elif instr_name in ['lw', 'lb', 'lh', 'lbu', 'lhu']:
                if len(args) != 2:
                    raise ValueError(f"Line {line_num}: '{instr_name}' expects 2 arguments: rd, offset(rs1).")
                rd = parse_register(args[0])
                mem_op = re.match(r'^(-?(?:0x[0-9a-f]+|\d+))\((\w+)\)$', args[1])
                if not mem_op:
                    raise ValueError(f"Line {line_num}: Invalid memory operand '{args[1]}' for {instr_name}.")
                imm, rs1 = int(mem_op.group(1), 0), parse_register(mem_op.group(2))
                check_imm(imm, I_TYPE_IMM_MIN, I_TYPE_IMM_MAX, instr_name)
                funct3_map = {'lw': F3_LW, 'lb': F3_LB, 'lh': F3_LH, 'lbu': F3_LBU, 'lhu': F3_LHU}
                mc = encode_i(imm, rs1, funct3_map[instr_name], rd, OPCODE_LOAD)

            elif instr_name in ['sw', 'sb', 'sh']:
                if len(args) != 2:
                    raise ValueError(f"Line {line_num}: '{instr_name}' expects 2 arguments: rs2, offset(rs1).")
                rs2 = parse_register(args[0])
                mem_op = re.match(r'^(-?(?:0x[0-9a-f]+|\d+))\((\w+)\)$', args[1])
                if not mem_op:
                    raise ValueError(f"Line {line_num}: Invalid memory operand '{args[1]}' for {instr_name}.")
                imm, rs1 = int(mem_op.group(1), 0), parse_register(mem_op.group(2))
                check_imm(imm, S_TYPE_IMM_MIN, S_TYPE_IMM_MAX, instr_name)
                funct3_map = {'sw': F3_SW, 'sb': F3_SB, 'sh': F3_SH}
                mc = encode_s(imm, rs2, rs1, funct3_map[instr_name], OPCODE_STORE)

            elif instr_name in ['beq', 'bne', 'blt', 'bge', 'bltu', 'bgeu']:
                if len(args) != 3:
                    raise ValueError(f"Line {line_num}: '{instr_name}' expects 3 arguments (rs1, rs2, label_or_offset).")
                rs1, rs2, target = parse_register(args[0]), parse_register(args[1]), args[2]
                if target in symbol_table:
                    imm = symbol_table[target] - current_address
                else:
                    try:
                        imm = int(target, 0)
                    except ValueError:
                        raise ValueError(f"Line {line_num}: Undefined label '{target}'.")
                check_imm(imm, B_IMM_MIN, B_IMM_MAX, instr_name)
                funct3_map = {'beq': F3_BEQ, 'bne': F3_BNE, 'blt': F3_BLT, 'bge': F3_BGE, 'bltu': F3_BLTU, 'bgeu': F3_BGEU}
                mc = encode_b(imm, rs2, rs1, funct3_map[instr_name], OPCODE_BRANCH)

            elif instr_name == 'jal':
                if len(args) != 2:
                    raise ValueError(f"Line {line_num}: 'jal' expects 2 arguments (rd, label_or_offset).")
                rd, target = parse_register(args[0]), args[1]
                if target in symbol_table:
                    imm = symbol_table[target] - current_address
                else:
                    try:
                        imm = int(target, 0)
                    except ValueError:
                        raise ValueError(f"Line {line_num}: Undefined label '{target}'.")
                check_imm(imm, J_IMM_MIN, J_IMM_MAX, instr_name)
                mc = encode_j(imm, rd, OPCODE_JAL)

            else:
                raise ValueError(f"Line {line_num}: Unsupported instruction '{instr_name}'.")

            machine_code.append(mc)
            disassembly[current_address] = original_line
            current_address += 4

    return {'machine_code': machine_code, 'disassembly': disassembly}, expansion_log

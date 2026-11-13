# riscv_core.py
from riscv_defs import *

def to_signed_32(value):
    """Converts a 32-bit unsigned value to a signed integer."""
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value & 0x80000000 else value

def _sign_extend_12(value):
    """Sign-extends a 12-bit value to a full integer."""
    value &= 0xFFF
    if value & 0x800:  # Check the 12th bit (the sign bit)
        return value - 0x1000
    return value

def _sign_extend_13(value):
    """Sign-extends a 13-bit branch offset to a full integer."""
    value &= 0x1FFF
    if value & 0x1000:
        return value - 0x2000
    return value

def _sign_extend_21(value):
    """Sign-extends a 21-bit jump offset to a full integer."""
    value &= 0x1FFFFF
    if value & 0x100000:
        return value - 0x200000
    return value

class RiscVCore:
    def __init__(self, mem_size=4096):
        self.mem = bytearray(mem_size)
        self.loaded_program_mc = []  # Store the initial machine code for resets
        self.base_address = 0
        self.halted = False
        self.error_msg = None
        self.reset()  # Call reset to initialize state

    def reset(self, reset_vector=None):
        """Resets the CPU state (PC, registers) and reloads program memory."""
        self.regs = [0] * 32
        self.pc = self.base_address if reset_vector is None else reset_vector
        self.cycles = 0
        self.halted = False
        self.error_msg = None
        # Reload program into memory from our backup
        self.load_program(self.loaded_program_mc, self.base_address)

    def load_program(self, machine_code, base_address=0):
        """Loads machine code into memory and keeps a backup for resets."""
        self.loaded_program_mc = list(machine_code)
        self.base_address = base_address
        self.mem = bytearray(len(self.mem))  # Clear memory
        for i, code in enumerate(self.loaded_program_mc):
            if code is not None:
                addr = base_address + i * 4
                if 0 <= addr <= len(self.mem) - 4:
                    self.mem[addr:addr+4] = (code & 0xFFFFFFFF).to_bytes(4, 'little', signed=False)

    def step(self):
        """Fetches, decodes, and executes a single instruction."""
        if self.halted:
            return False

        if not (0 <= self.pc <= len(self.mem) - 4 and self.pc % 4 == 0):
            self.halted = True
            self.error_msg = f"PC out of bounds or misaligned: 0x{self.pc:08x}"
            return False  # Halt execution if PC is out of bounds or misaligned

        # 1. FETCH
        instr_mc = int.from_bytes(self.mem[self.pc : self.pc+4], 'little')
        if instr_mc == 0:
            self.halted = True
            return False  # Stop on null instruction (end of program)

        # 2. DECODE
        opcode = instr_mc & OPCODE_MASK
        rd, rs1, rs2 = (instr_mc >> 7) & 0x1F, (instr_mc >> 15) & 0x1F, (instr_mc >> 20) & 0x1F
        funct3, funct7 = (instr_mc >> 12) & 0x7, (instr_mc >> 25) & 0x7F
        next_pc = (self.pc + 4) & 0xFFFFFFFF

        # 3. EXECUTE
        if opcode == OPCODE_LUI:
            imm = instr_mc & 0xFFFFF000
            if rd != 0:
                self.regs[rd] = to_signed_32(imm)

        elif opcode == OPCODE_AUIPC:
            imm = instr_mc & 0xFFFFF000
            if rd != 0:
                self.regs[rd] = to_signed_32(self.pc + imm)

        elif opcode == OPCODE_LOAD:
            imm = _sign_extend_12(instr_mc >> 20)
            addr = (self.regs[rs1] + imm) & 0xFFFFFFFF
            if funct3 == F3_LB:
                if not (0 <= addr < len(self.mem)):
                    self.halted = True
                    self.error_msg = f"Load byte address out of bounds: 0x{addr:08x}"
                    return False
                val = self.mem[addr]
                if rd != 0:
                    self.regs[rd] = val - 0x100 if val & 0x80 else val
            elif funct3 == F3_LH:
                if not (0 <= addr <= len(self.mem) - 2):
                    self.halted = True
                    self.error_msg = f"Load halfword address out of bounds: 0x{addr:08x}"
                    return False
                if rd != 0:
                    self.regs[rd] = int.from_bytes(self.mem[addr:addr+2], 'little', signed=True)
            elif funct3 == F3_LW:
                if not (0 <= addr <= len(self.mem) - 4):
                    self.halted = True
                    self.error_msg = f"Load word address out of bounds: 0x{addr:08x}"
                    return False
                if rd != 0:
                    self.regs[rd] = int.from_bytes(self.mem[addr:addr+4], 'little', signed=True)
            elif funct3 == F3_LBU:
                if not (0 <= addr < len(self.mem)):
                    self.halted = True
                    self.error_msg = f"Load byte unsigned address out of bounds: 0x{addr:08x}"
                    return False
                if rd != 0:
                    self.regs[rd] = self.mem[addr]
            elif funct3 == F3_LHU:
                if not (0 <= addr <= len(self.mem) - 2):
                    self.halted = True
                    self.error_msg = f"Load halfword unsigned address out of bounds: 0x{addr:08x}"
                    return False
                if rd != 0:
                    self.regs[rd] = int.from_bytes(self.mem[addr:addr+2], 'little', signed=False)
            else:
                self.halted = True
                self.error_msg = f"Invalid LOAD funct3: {funct3}"
                return False

        elif opcode == OPCODE_STORE:
            imm_raw = ((instr_mc >> 25) << 5) | ((instr_mc >> 7) & 0x1F)
            imm = _sign_extend_12(imm_raw)
            addr = (self.regs[rs1] + imm) & 0xFFFFFFFF
            if funct3 == F3_SB:
                if not (0 <= addr < len(self.mem)):
                    self.halted = True
                    self.error_msg = f"Store byte address out of bounds: 0x{addr:08x}"
                    return False
                self.mem[addr] = self.regs[rs2] & 0xFF
            elif funct3 == F3_SH:
                if not (0 <= addr <= len(self.mem) - 2):
                    self.halted = True
                    self.error_msg = f"Store halfword address out of bounds: 0x{addr:08x}"
                    return False
                self.mem[addr:addr+2] = (self.regs[rs2] & 0xFFFF).to_bytes(2, 'little', signed=False)
            elif funct3 == F3_SW:
                if not (0 <= addr <= len(self.mem) - 4):
                    self.halted = True
                    self.error_msg = f"Store word address out of bounds: 0x{addr:08x}"
                    return False
                self.mem[addr:addr+4] = (self.regs[rs2] & 0xFFFFFFFF).to_bytes(4, 'little', signed=False)
            else:
                self.halted = True
                self.error_msg = f"Invalid STORE funct3: {funct3}"
                return False

        elif opcode == OPCODE_IMM:
            imm = _sign_extend_12(instr_mc >> 20)
            shamt = rs2
            res = None
            if funct3 == F3_ADD_SUB:
                res = to_signed_32(self.regs[rs1] + imm)
            elif funct3 == F3_SLT:
                res = 1 if self.regs[rs1] < imm else 0
            elif funct3 == F3_SLTU:
                res = 1 if (self.regs[rs1] & 0xFFFFFFFF) < (imm & 0xFFFFFFFF) else 0
            elif funct3 == F3_XOR:
                res = to_signed_32(self.regs[rs1] ^ imm)
            elif funct3 == F3_OR:
                res = to_signed_32(self.regs[rs1] | imm)
            elif funct3 == F3_AND:
                res = to_signed_32(self.regs[rs1] & imm)
            elif funct3 == F3_SLL and funct7 == F7_SRL:
                res = to_signed_32(self.regs[rs1] << shamt)
            elif funct3 == F3_SRL_SRA:
                if funct7 == F7_SRA:
                    res = to_signed_32(self.regs[rs1] >> shamt)
                elif funct7 == F7_SRL:
                    res = to_signed_32((self.regs[rs1] & 0xFFFFFFFF) >> shamt)
            if res is None:
                self.halted = True
                self.error_msg = f"Invalid I-type instruction: 0x{instr_mc:08x}"
                return False
            if rd != 0:
                self.regs[rd] = res

        elif opcode == OPCODE_REG:
            val1, val2 = self.regs[rs1], self.regs[rs2]
            res = None
            if funct3 == F3_ADD_SUB:
                if funct7 == F7_SUB:
                    res = to_signed_32(val1 - val2)
                elif funct7 == F7_ADD:
                    res = to_signed_32(val1 + val2)
            elif funct3 == F3_SLL and funct7 == 0:
                res = to_signed_32(val1 << (val2 & 0x1F))
            elif funct3 == F3_SLT and funct7 == 0:
                res = 1 if val1 < val2 else 0
            elif funct3 == F3_SLTU and funct7 == 0:
                res = 1 if (val1 & 0xFFFFFFFF) < (val2 & 0xFFFFFFFF) else 0
            elif funct3 == F3_XOR and funct7 == 0:
                res = to_signed_32(val1 ^ val2)
            elif funct3 == F3_SRL_SRA:
                if funct7 == F7_SRA:
                    res = to_signed_32(val1 >> (val2 & 0x1F))
                elif funct7 == F7_SRL:
                    res = to_signed_32((val1 & 0xFFFFFFFF) >> (val2 & 0x1F))
            elif funct3 == F3_OR and funct7 == 0:
                res = to_signed_32(val1 | val2)
            elif funct3 == F3_AND and funct7 == 0:
                res = to_signed_32(val1 & val2)
            if res is None:
                self.halted = True
                self.error_msg = f"Invalid R-type instruction: 0x{instr_mc:08x}"
                return False
            if rd != 0:
                self.regs[rd] = res

        elif opcode == OPCODE_BRANCH:
            raw_b_imm = (((instr_mc >> 31) & 0x1) << 12) | (((instr_mc >> 7) & 0x1) << 11) | (((instr_mc >> 25) & 0x3F) << 5) | (((instr_mc >> 8) & 0xF) << 1)
            imm = _sign_extend_13(raw_b_imm)
            val1, val2 = self.regs[rs1], self.regs[rs2]
            branch_taken = (
                (funct3 == F3_BEQ and val1 == val2) or
                (funct3 == F3_BNE and val1 != val2) or
                (funct3 == F3_BLT and val1 < val2) or
                (funct3 == F3_BGE and val1 >= val2) or
                (funct3 == F3_BLTU and (val1 & 0xFFFFFFFF) < (val2 & 0xFFFFFFFF)) or
                (funct3 == F3_BGEU and (val1 & 0xFFFFFFFF) >= (val2 & 0xFFFFFFFF))
            )
            if branch_taken:
                next_pc = (self.pc + imm) & 0xFFFFFFFF

        elif opcode == OPCODE_JAL:
            raw_j_imm = (((instr_mc >> 31) & 0x1) << 20) | (((instr_mc >> 12) & 0xFF) << 12) | (((instr_mc >> 20) & 0x1) << 11) | (((instr_mc >> 21) & 0x3FF) << 1)
            imm = _sign_extend_21(raw_j_imm)
            if rd != 0:
                self.regs[rd] = to_signed_32(next_pc)
            next_pc = (self.pc + imm) & 0xFFFFFFFF

        elif opcode == OPCODE_JALR:
            imm = _sign_extend_12(instr_mc >> 20)
            if rd != 0:
                self.regs[rd] = to_signed_32(next_pc)
            next_pc = ((self.regs[rs1] + imm) & ~1) & 0xFFFFFFFF

        else:
            self.halted = True
            self.error_msg = f"Unsupported opcode: 0x{opcode:02x}"
            return False

        self.regs[0] = 0
        self.pc = next_pc
        self.cycles += 1
        return True  # Indicate successful step

    def run(self, max_cycles=5000):
        """Continuously steps until the program ends or max_cycles is hit."""
        start_cycles = self.cycles
        while (self.cycles - start_cycles) < max_cycles:
            if not self.step():
                break  # Stop if step() indicates the program is done

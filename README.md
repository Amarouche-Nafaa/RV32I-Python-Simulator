# 🖥️ RISC-V RV32I Simulator, Assembler & Microarchitecture Model

![RISC-V](https://img.shields.io/badge/ISA-RISC--V_RV32I-blue?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)

An interactive **32-bit RISC-V (RV32I) Instruction Set Simulator, Two-Pass Assembler, Visual Debugger, and Cycle-Accurate Microarchitecture Model** built in Python and Streamlit.

Originally inspired by [Chip Design with Rashid's](https://github.com/ChipDesignRashid) RISC-V educational series, this version includes a hardened two-pass assembler, signed/unsigned 32-bit arithmetic fixes, strict memory bounds checking, and a block-level hardware datapath model ready for SystemVerilog RTL translation.

---

## ✨ Key Features

- **Full RV32I Base Integer Instruction Set (37 Instructions):**
  - **R-Type (10):** `add`, `sub`, `sll`, `slt`, `sltu`, `xor`, `srl`, `sra`, `or`, `and`
  - **I-Type ALU (9):** `addi`, `slti`, `sltiu`, `xori`, `ori`, `andi`, `slli`, `srli`, `srai`
  - **Loads (5):** `lw`, `lh`, `lb`, `lhu`, `lbu`
  - **Stores (3):** `sw`, `sh`, `sb`
  - **Branches (6):** `beq`, `bne`, `blt`, `bge`, `bltu`, `bgeu`
  - **Jumps (2):** `jal`, `jalr` (supports both `jalr rd, rs1, imm` and `jalr rd, imm(rs1)`)
  - **U-Type (2):** `lui`, `auipc`
- **Two-Pass Assembler & Pseudo-Instruction Expander:**
  - Supports `li` (full 32-bit signed/unsigned constants via automatic `lui` + `addi` expansion), `mv`, `j`, `jr`, `nop`, and `ret`.
  - Supports both standalone and inline labels (e.g., `loop: addi t0, t0, 1`).
- **Interactive Visual Debugger (Streamlit GUI):**
  - **Step-by-Step Execution:** Single-step (`⏯️ Step`), continuous execution (`⏩ Run to End`), and hardware reset (`🔄 Reset`).
  - **Color-Coded Register File:** All 32 registers (`x0`–`x31`) grouped by RISC-V ABI role (Special, Temporary, Saved, Arguments) with live hex/decimal views.
  - **Live Memory Viewers:**
    - **Instruction Memory:** Highlights the active Program Counter (`PC`) in yellow with live disassembly.
    - **Stack Memory:** Dynamically tracks and highlights the Stack Pointer (`sp`) in orange.
    - **Data Memory:** Inspects word-aligned RAM contents (`0x0200`–`0x02FC`).
- **Hardware-Mapped Microarchitecture Notebooks:**
  - Models physical hardware blocks (`PCState`, `RegisterFile`, `InstructionMemory`, `DataMemory`, `Controller`, `ALU`, `BranchControlUnit`, `LoadAlignmentUnit`, `StoreAlignmentUnit`) to bridge software simulation and SystemVerilog RTL design.

---

## 📂 Folder Structure

```text
RISC-V-Simulator/
├── .gitignore
├── README.md
├── requirements.txt                  # Python dependencies
├── app.py                            # Main Streamlit GUI entry point
├── style.css                         # Custom CSS styling for registers & memory views
├── assembler.py                      # Two-pass RV32I assembler & pseudo-instruction expander
├── riscv_core.py                     # RV32I execution engine & byte-addressable memory
├── riscv_defs.py                     # Opcodes, funct3/funct7 constants, encoders & disassembler
├── instruction_examples.py           # Pre-built RV32I assembly demo programs
└── notebooks/                        # Hardware microarchitecture & verification notebooks
    ├── osoc1_core_uarch.ipynb        # Full block-level RV32I microarchitecture & testbench
    └── osoc1_core_uarch_video6.ipynb # Early single-cycle datapath prototype
```

---

## 🚀 Getting Started & Setup Guide

### 1. Prerequisites

- **Python 3.10+** installed on your system.
- **Git** (optional, for cloning and version control).

### 2. Create & Activate a Virtual Environment

Open your terminal in the project root directory and run:

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Launch the Simulator GUI

```bash
streamlit run app.py
```

Your default browser will automatically open the simulator at `http://localhost:8501`.

---

## 🛠️ How to Use the Simulator

1. **Load an Example or Write Custom Assembly:**
   - Click **"Show References and Examples"** at the top of the app to load pre-configured demos for R-Type, I-Type, Memory Operations, Branches, Function Calls & Stack frames, Upper Immediates, or Pseudo-Instructions.
   - Or write your own RV32I assembly program directly in the **Assembly Program** editor.
2. **Assemble & Load (`▶️ Assemble & Load`):**
   - Runs the two-pass assembler, logs any expanded pseudo-instructions (`li`, `j`, `mv`, `ret`), and loads the 32-bit little-endian machine code into instruction memory starting at `0x0000`.
3. **Debug Execution:**
   - Click **`⏯️ Step`** to advance one clock cycle at a time and watch `PC`, `sp`, CPU registers, and memory words update in real time.
   - Click **`⏩ Run to End`** to execute until the program reaches empty memory (`0x00000000`), triggers a runtime trap, or hits the 5,000-cycle watchdog limit.

---

## 🔧 Improvements & Bug Fixes Included in This Repo

Compared to the original reference implementation, this repository includes several critical fixes:

- **Fixed 32-bit `li` Immediate Expansion:** Properly sign-extends and masks 32-bit constants (such as `0xFFFFFFFF`, `-2049`, and `0x7FFFF800`) into `lui` + `addi` without triggering false range errors.
- **Fixed Infinite Fall-Through Loops in Demo Programs:** Added proper program termination branches to `JUMP_CALL_EXAMPLES` and `PSEUDO_INSTRUCTION_EXAMPLES` so function returns (`ret` / `jalr`) do not fall through or loop back to `0x0000`.
- **Dual `jalr` Syntax & `jr` Support:** The assembler accepts both `jalr rd, rs1, imm` and `jalr rd, imm(rs1)` (matching the disassembler output), as well as `jr rs1`.
- **Strict Shift Immediate (`shamt`) Bounds Checking:** Enforces `[0, 31]` shift bounds on `slli`, `srli`, and `srai` so invalid shift amounts cannot corrupt the `funct7` bitfield.
- **Clean Runtime Trap Halting:** Out-of-bounds memory accesses (`lw`, `lh`, `lb`, `sw`, `sh`, `sb`) now halt the core cleanly and display a **Runtime Trap** message in the UI rather than freezing `PC`.

---

## 📚 Credits & Acknowledgments

- **Original Concept & Tutorials:** [Chip Design with Rashid](https://github.com/ChipDesignRashid/RISC-Sim-by-Rashid) ([YouTube Playlist](https://youtube.com/playlist?list=PL0-xus8sJBCSjjaf-MTtGEdh4XgXRQPgz)).

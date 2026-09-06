# Equipment instance resolver (CUSA03173 01.09)

This is the externally readable branch of the game's descriptor resolver. It
was recovered on 2026-09-06 from a read-only `ReadProcessMemory` capture of the
decrypted eboot mapped by shadPS4 0.18.0. The source eboot SHA-256 was
`d65f0b4f01d59166aed16f8604196d8b7dd805abbf0758b356e8f1354c9429f9`.

The complete function at eboot RVA `0x1A89070` is `0x154` bytes and has SHA-256
`6277cd15112dde76f1bbc3e8d75b72a31ab45a61743abb179993fbd65c98aa33`.
Its allocated-instance branch reduces to:

```text
eax = descriptor->raw_id
compact = eax & 0x00ffffff
require compact != 0x00ffffff
require compact & 0x00800000
registry = *(u64 *)(eboot + 0x553e990)
index = compact & 0xffff
require index != 0xffff
object = *(u64 *)(registry + index * 8 + 8)
require object != 0
require *(u32 *)(object + 8) == eax
descriptor->internal_pointer = object
descriptor->normalized_id = *(u32 *)(object + 0x0c)
```

The instructions establishing the data traversal are:

```text
1A890BA  lea r14,[rip+3AB58CF]       ; eboot+553E990
1A890C1  mov rcx,[r14]
1A89111  movzx edx,dx               ; low-16 instance index
1A8911C  mov rcx,[rcx+rdx*8+8]
1A89126  cmp [rcx+8],eax             ; full handle identity guard
1A8912B  mov [rbx+8],rcx             ; resolved object
1A8912F  mov eax,[rcx+0C]
1A89132  mov [rbx+10],eax            ; normalized weapon row
```

The shipped grant path separately established current durability at object
offset `+0x18`. No gem-slot or attached-gem offsets are currently evidenced.
Diagnostic captures larger than `0x1c` are raw memory windows beginning at the
resolved object; `0x100` is a diagnostic window size, not a claimed object size.

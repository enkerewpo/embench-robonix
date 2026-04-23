# Phase A — phase_a_20260423_231222

**Tasks**: 20  **Success**: 14  **SR**: 70.0%  (95% Wilson CI [48.1%, 85.5%])

## Per-task
| # | episode | instruction | success | steps | turns | wall s |
|---|---|---|---|---|---|---|
| eb_base_000 | 0 | Move one of the pear items to the indicated sofa. | ✓ | 8 | 2 | 24.32 |
| eb_base_001 | 1 | Find a orange on the TV stand and move it to the sink. | ✓ | 1 | 2 | 6.09 |
| eb_base_002 | 2 | Take an pear and transfer it to the allocated left counter. | ✗ | 6 | 2 | 18.5 |
| eb_base_003 | 3 | Find a orange and move it to the right counter. | ✓ | 4 | 2 | 10.19 |
| eb_base_004 | 4 | On the right counter, I need a toy airplane and a orange. | ✗ | 10 | 2 | 22.78 |
| eb_base_005 | 5 | I left the fridge open. Can you help? | ✓ | 2 | 2 | 5.31 |
| eb_base_006 | 6 | On the TV stand I need you to put a plate. | ✓ | 5 | 2 | 18.74 |
| eb_base_007 | 7 | Detach the strawberry from the right counter. | ✓ | 2 | 2 | 8.31 |
| eb_base_008 | 8 | Bring a banana and a can to the left counter. | ✗ | 15 | 2 | 35.07 |
| eb_base_009 | 9 | I left my mug on the sofa, can you bring it to the left coun | ✓ | 4 | 2 | 10.04 |
| eb_base_010 | 10 | Find a toy airplane and move it to the right counter. | ✓ | 3 | 2 | 13.23 |
| eb_base_011 | 11 | Hey, on the sink, I accidentally left my plate, can you brin | ✓ | 4 | 2 | 10.14 |
| eb_base_012 | 12 | I need a book on the TV stand. Can you help? | ✓ | 3 | 2 | 10.57 |
| eb_base_013 | 13 | The fridge door is open because of my mistake. Can you close | ✓ | 2 | 2 | 9.29 |
| eb_base_014 | 14 | On the left counter, remove the lego. | ✗ | 2 | 2 | 8.39 |
| eb_base_015 | 15 | The sink needs an hammer and a cup on it. | ✗ | 13 | 2 | 37.22 |
| eb_base_016 | 16 | The rubriks cube is on the right counter but you should move | ✓ | 4 | 2 | 11.95 |
| eb_base_017 | 17 | Put both an rubriks cube and a lid onto the left counter. | ✗ | 7 | 2 | 17.47 |
| eb_base_018 | 18 | Displace the spatula from the sink. | ✓ | 1 | 2 | 5.37 |
| eb_base_019 | 19 | Find a wrench and move it to the left counter. | ✓ | 7 | 2 | 16.81 |

## Comparison — EB-Habitat base (paper Table 2)
| Model | SR |
|---|---|
| **Robonix (this run)** | **70.0%** |
| Claude-3.5-Sonnet | 96.0% |
| Llama-3.2-90B-Vision | 94.0% |
| Gemini-1.5-Pro | 92.0% |
| GPT-4o | 86.0% |
| Gemini-2.0-flash | 82.0% |
| InternVL2_5-78B | 80.0% |
| Gemini-1.5-flash | 76.0%  ← peer |
| GPT-4o-mini | 74.0%  ← peer |
| Qwen2-VL-72B | 70.0%  ← peer |
| Llama-3.2-11B-Vision | 70.0%  ← peer |
| InternVL2_5-38B | 60.0%  ← peer |
| Qwen2-VL-7B | 48.0% |
| InternVL2_5-8B | 36.0% |

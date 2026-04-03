# Robot Mission MAS 2026
## Self-organization of robots in a hostile environment

- **Group number:** 22
- **Members:**
  - Gabriel Anjos Moura
  - Vinícius da Mata e Mota
  - Nicholas Oliveira Rodrigues Bragança

---

## Project Structure

| File | Description |
|---|---|
| `actions.py` | Catalog of action factories returned by `deliberate` (`move`, `pick`, `transform`, `transform_orphan`, `drop`, `dispose`, `idle`). |
| `agents.py` | Green, yellow, and red robot classes implementing the perception → deliberation → action cycle. |
| `objects.py` | Passive environment objects: `Waste`, `RadioactivityCell`, `WasteDisposalZone`. |
| `model.py` | Mesa model: environment initialization, action execution (`do`), and `DataCollector`. |
| `server.py` | Solara visualization server. |
| `run.py` | Quick headless execution in script mode. |
| `config.py` | Default parameters and visual constants. |

---

## Environment

The grid (default **15 × 10**) is divided into three vertical zones of equal width:

| Zone | Columns | Radioactivity | Robots allowed |
|---|---|---|---|
| `z1` (green) | 0 – 4 | 0.00 – 0.33 | Green, Yellow, Red |
| `z2` (yellow) | 5 – 9 | 0.33 – 0.66 | Yellow, Red |
| `z3` (red) | 10 – 14 | 0.66 – 1.00 | Red only |

A single **Waste Disposal Zone** is placed at a random row on the rightmost column (x = 14).

Waste is created at start and placed randomly within its matching zone:
- **Green waste** → `z1`
- **Yellow waste** → `z2`
- **Red waste** → `z3`

---

## Robot Strategy

All robots share the same **perception → deliberation → action** loop defined in `BaseRobotAgent.step_agent()`. Each step, a robot:
1. Receives **percepts** from the model (visible tiles, waste positions, allowed moves).
2. Updates its **knowledge** dictionary (includes a 25-step positional history and a full memory map of seen tiles).
3. Runs **`deliberate(knowledge)`** to choose an action.
4. Sends the action to the model via **`do()`** and stores the returned percepts.

Movement always uses **Manhattan-distance minimisation** over robot-free neighbouring cells. A robot will `idle` if all neighbours are blocked.

---

### 🟢 Green Robot — `GreenRobotAgent`

**Zone:** `z1` only | **Collects:** green waste | **Produces:** yellow waste | **Capacity:** 2

#### Normal collection cycle

1. **Explore.** If carrying nothing and green waste is visible, move towards the nearest one (Manhattan distance).
2. **Pick.** When on the same cell as a green waste item, pick it up.
3. **Pair.** Collect a second green waste item.
4. **Transform.** With 2 greens in cargo, immediately execute `transform` → cargo becomes 1 yellow.
5. **Deliver.** Move eastward to the **z1 east border** (column 4, any row). Choose the nearest border cell.
6. **Drop.** Drop the yellow waste at the border cell.
7. **Vacate.** If the border cell now contains yellow waste but the robot is empty, retreat one step west (or to a random free cell) so that yellow robots can access the drop point.
8. **Repeat.**

#### Fallback exploration

When no green waste is visible and the robot is empty, it uses `_get_fallback_target` to walk towards the east border:
- If the robot is already west of the border, move directly to the nearest unvisited border cell.
- Otherwise, prefer border cells not seen in the last 25 steps; fall back to the nearest non-current border cell.

This keeps robots sweeping the zone rather than clustering in one spot.

---

### 🟡 Yellow Robot — `YellowRobotAgent`

**Zones:** `z1` and `z2` | **Collects:** yellow waste | **Produces:** red waste | **Capacity:** 2

#### Normal collection cycle

1. **Explore** `z1` and `z2` for yellow waste, moving towards the nearest item.
2. **Pick** a yellow waste unit on the current cell.
3. **Pair.** Collect a second yellow waste unit.
4. **Transform.** With 2 yellows in cargo, execute `transform` → cargo becomes 1 red.
5. **Deliver.** Move eastward to the **z2 east border** (column 9, any row).
6. **Drop** the red waste at the border cell.
7. **Repeat.**

Yellow robots may enter `z1` to collect yellow waste dropped there by green robots after their delivery step.

#### Fallback exploration

Same logic as green robots, but targeting the z2 east border cells.

---

### 🔴 Red Robot — `RedRobotAgent`

**Zones:** `z1`, `z2`, `z3` (all zones) | **Collects:** red waste | **No transformation** | **Capacity:** 1

#### Cycle

1. **Search.** Move towards the nearest visible red waste across all zones.
2. **Pick** a red waste unit on the current cell (capacity = 1).
3. **Deliver.** Move directly to the disposal position (rightmost column, fixed row).
4. **Dispose.** When standing on the disposal cell, execute `dispose` → waste count increments and cargo clears.
5. **Repeat.** If no red waste is visible, move to a random free neighbouring cell to continue searching.

---

## Orphan Waste Handling

When the total quantity of waste of a given type is **odd**, one unit will be left without a pair and can never be transformed through the standard 2-into-1 rule. The system handles this via **forced promotion** (`transform_orphan`).

### Detection

At every step, each robot distinguishes:
- **Normal waste** — `visible_waste_positions[type]`: waste items not flagged as orphan.
- **Orphan waste** — `orphan_waste_positions[type]`: waste items flagged as orphan (dropped by a previous generation of robots).

A robot decides it can handle orphan waste (`can_pick_orphans = True`) when:
- It is **already carrying 1 item** and wants to pair it, **or**
- There are **no non-orphan items left** of that type anywhere in the accessible zones — meaning no pair will ever form.

### Resolution

When a robot is carrying **exactly 1 item** of its collectible type and `target_greens` / `target_yellows` is empty (no more waste to collect), instead of dropping the lone item on the grid (where no downstream robot could handle it), it calls `transform_orphan()`:

| Situation | Action | Result |
|---|---|---|
| Green robot holds 1 green, no more greens | `transform_orphan()` | cargo becomes **yellow** |
| Yellow robot holds 1 yellow, no more yellows | `transform_orphan()` | cargo becomes **red** |

The robot then proceeds with its normal delivery step: it carries the promoted item to the east border and drops it, where the next tier of robots picks it up as a regular item.

This ensures the full pipeline never stalls: every waste unit, whether paired or not, eventually reaches the disposal zone.

### Why not `drop(orphan=True)`?

An earlier design dropped the lone item at the zone border with an `orphan` flag. This was broken because the downstream robot (e.g. yellow) only collects its own type (yellow) — a green orphan dropped at the border would sit there forever. `transform_orphan` avoids this by promoting the item in-cargo before delivery.

---

## How to Run

### Headless simulation

```bash
conda activate project-mas-env
python run.py
```

### Interactive visualization (Solara)

```bash
conda activate project-mas-env
solara run server.py
```

---

## Default Parameters (`config.py`)

| Parameter | Default |
|---|---|
| Grid width | 15 |
| Grid height | 10 |
| Green robots | 4 |
| Yellow robots | 3 |
| Red robots | 2 |
| Initial green waste | 24 |
| Initial yellow waste | 12 |
| Initial red waste | 12 |
| Max steps | 300 |

---

## Extension Points

- Specialize `deliberate()` further (e.g. communication between agents).
- Enhance `knowledge["memory"]` with decay or shared maps.
- Change the exploration / transport policy for global efficiency optimization.
- Add new metrics to the `DataCollector`.
- Implement dynamic waste generation during the simulation.

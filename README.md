# Robot Mission MAS 2026:  
## Self-organization of robots in a hostile environment

- Group number: 22
- Members: 
  - Gabriel	Anjos Moura
  - Vinícius	da Mata e Mota
  - Nicholas	Oliveira Rodrigues Bragança


## Structure

- `actions.py`: simple catalog of actions returned by `deliberate`.
- `agents.py`: green, yellow, and red robots with a perception → deliberation → action cycle.
- `objects.py`: passive environment objects (`Waste`, `RadioactivityCell`, `WasteDisposalZone`).
- `model.py`: Mesa model, environment initialization, execution of actions (`do`), and `DataCollector`.
- `server.py`: Solara visualization in the same style as the previous exercise.
- `run.py`: quick execution in script mode.
- `config.py`: default parameters and visual constants.

## How to run

### 1. Simple simulation

```bash
python -m robot_mission_mas2026.run
```

### 2. Visualization with Solara

```bash
solara run robot_mission_mas2026/server.py
```

## Points already prepared for extension

- specialize the `deliberate()` function of each robot;
- add communication between agents;
- enhance the memory in `knowledge["memory"]`;
- change the exploration / transport policy for global optimization;
- include new metrics in the `DataCollector`.

## Notes

- The current version covers **Step 1** of the assignment: agents without communication, with a modular architecture.
- The transformation was implemented as follows:
  - 2 greens → 1 yellow
  - 2 yellows → 1 red
  - 1 red → disposal in the final zone
- The robots already respect the zone restrictions:
  - green: `z1`
  - yellow: `z1` and `z2`
  - red: `z1`, `z2`, and `z3`

"""Experiment configuration — the values used in the final notebook (Section 1).

Every setting that defines the experiment lives here, so the data generator,
the models and the scripts all read the same numbers.
"""

# Random seeds
DEV_SEED = 42            # development data: train / validation / internal test
TEST_SEED = 20261014     # independent test set (never used for training or tuning)

# Dataset size and operating conditions
N_NORMAL = 5000          # normal snapshots per dataset
N_ATTACK = 2000          # snapshots per attack type (3 types)
LOAD_MIN, LOAD_MAX = 0.80, 1.20   # per-bus load scaling of the IEEE 14-bus base case

# Attacks: 1–3 % of the true measurement; the slack bus (Bus 1) is never attacked
ATTACK_MIN, ATTACK_MAX = 0.010, 0.030
VA_ATTACK_MAX_DEG = 0.5  # angle bias at the maximum attack magnitude (degrees)

# Measurement noise (one standard deviation)
VM_NOISE_STD = 0.002     # voltage magnitude, p.u.
VA_NOISE_STD = 0.115     # voltage angle, degrees (0.002 rad)
PD_NOISE_REL = 0.01      # load active power, fraction of value
QD_NOISE_REL = 0.01      # load reactive power, fraction of value
PG_NOISE_REL = 0.01      # generator active power, fraction of value
QG_NOISE_REL = 0.01      # generator reactive power, fraction of value
PD_NOISE_FLOOR = 0.01    # minimum magnitude used to scale relative noise
QD_NOISE_FLOOR = 0.01

# Physics validation layer
USE_S_LOADING = False    # thermal-loading check off: IEEE 14-bus ratings are 9900 MVA placeholders
S_LOADING_THRESHOLD = 0.95
PHYSICS_Z_GRID = (2.0, 2.5, 3.0, 3.5, 4.0)   # z-score thresholds tried on validation normals
PHYSICS_VOTES = 2                            # checks that must agree at one bus
PHYSICS_MAX_VAL_FPR = 5.0                    # % — first Z whose validation false alarms are below this

# Split
SPLIT_SEED = 42
TEST_FRACTION = 0.30     # 70 / 15 / 15 (the 30 % is halved into validation and internal test)

# Autoencoder
AE_SEEDS = (42, 123, 456, 789)   # seed chosen by lowest validation loss
AE_LAYERS = (40, 24, 24, 24, 40) # 56 → 40 → 24 → 24 → 24 → 40 → 56
AE_EPOCHS = 100
AE_BATCH = 64
AE_LR = 1e-3

# Random Forest (attack type)
RF_PARAMS = dict(n_estimators=500, max_depth=None, min_samples_split=5,
                 class_weight="balanced", oob_score=True, random_state=42, n_jobs=-1)

# Localiser (one RF per bus)
LOC_PARAMS = dict(n_estimators=200, random_state=42, class_weight="balanced",
                  min_samples_split=5, n_jobs=-1)
LOC_THRESHOLD_GRID = tuple(t / 100 for t in range(20, 71))
FALSE_LOC_LIMIT = 0.05

# Fusion grid (searched on validation, best F1)
FUSION_W_RF = (0.3, 0.4, 0.5, 0.6)
FUSION_W_AE = (0.1, 0.2, 0.3)
FUSION_W_PH_RANGE = (0.1, 0.6)

ATTACK_TYPES = {0: "Normal", 1: "Additive", 2: "Scaling", 3: "Coordinated"}

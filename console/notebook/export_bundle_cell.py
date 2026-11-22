# ============================================================
# GridDefense | Export the trained system for the dashboard app (standalone)
# ============================================================
# HOW TO RUN (Colab):
#   1. Run notebook cells 1, 2 and 3 only (imports + pypower, Drive mount,
#      experiment CONFIG). Nothing else needs to be re-run.
#   2. Paste this whole cell below them and run it.
#
# WHAT IT DOES
#   • Loads the files the notebook already SAVED in OUT_DIR
#     (MyDrive/GridDefense/final_notebook). Nothing is trained or tuned here.
#   • Converts the autoencoder to plain numpy weights (the app has no TensorFlow)
#     and checks the numpy version gives the same output as Keras.
#   • Copies the independent test set (seed 20261014) and attaches the notebook's
#     own Section 10 decisions from results/alarm_log.csv, so the app can prove
#     it reproduces every alarm and every named bus.
#   • Re-checks, here in Colab, that the saved AE and RF reproduce alarm_log's
#     ae_score and rf_score (proves these are the files that produced the results).
#   • Writes a manifest: export time, library versions, MD5 of every source file,
#     feature counts and thresholds, and a SHA-256 fingerprint of the bundle.
#
# OUTPUT: MyDrive/GridDefense/app_bundle/  → download the whole folder.
# ============================================================
import os, json, glob, shutil, hashlib, platform, joblib, sklearn
import numpy as np, pandas as pd
from datetime import datetime, timezone

SRC = OUT_DIR                                        # from cell 2
BUNDLE = os.path.join(os.path.dirname(OUT_DIR), 'app_bundle')
os.makedirs(f'{BUNDLE}/results', exist_ok=True)

def _md5(p):
    h = hashlib.md5()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()

FILES = dict(ae='autoencoder.h5', scaler='scaler_ae.pkl', ae_json='ae_threshold.json',
             rf='rf_final.pkl', rf_cols='rf_feature_cols.pkl', loc='rf_loc_final_172feat.pkl',
             loc_cfg='loc_thresholds_and_config.pkl', physics='physics_params.npz',
             fusion='fusion_config.json', test=f'test_dataset_seed{TEST_SEED}.csv', dev='dev_dataset_raw.csv',
             alarm_log='results/alarm_log.csv')
missing = [f for f in FILES.values() if not os.path.exists(f'{SRC}/{f}')]
assert not missing, f'Missing in {SRC}: {missing} — run those notebook sections first'
SRC_MD5 = {f: _md5(f'{SRC}/{f}') for f in FILES.values()}

# ── 1. Load the saved parts ──
from tensorflow import keras
autoencoder_ = keras.models.load_model(f'{SRC}/{FILES["ae"]}', compile=False)
scaler_ae_ = joblib.load(f'{SRC}/{FILES["scaler"]}')
ae_json = json.load(open(f'{SRC}/{FILES["ae_json"]}'))
rf_model_ = joblib.load(f'{SRC}/{FILES["rf"]}')
rf_cols_ = list(joblib.load(f'{SRC}/{FILES["rf_cols"]}'))
rf_loc_ = joblib.load(f'{SRC}/{FILES["loc"]}')
loc_cfg = joblib.load(f'{SRC}/{FILES["loc_cfg"]}')
P = np.load(f'{SRC}/{FILES["physics"]}')
FUSION_ = json.load(open(f'{SRC}/{FILES["fusion"]}'))
test = pd.read_csv(f'{SRC}/{FILES["test"]}')
log = pd.read_csv(f'{SRC}/{FILES["alarm_log"]}', keep_default_na=False)
assert len(test) == len(log), f'test set has {len(test)} rows but alarm_log has {len(log)}'
assert (log['snapshot'].values == np.arange(len(log))).all(), 'alarm_log rows are not in snapshot order'

ae_cols_ = list(ae_json['feature_cols'])
check_names_ = list(FUSION_['physics_checks'])
N_B = 14
base_cols_ = ([f'Vm_{i+1}' for i in range(N_B)] + [f'Va_{i+1}' for i in range(N_B)] +
              [f'Pd_{i+1}' for i in range(N_B)] + [f'Qd_{i+1}' for i in range(N_B)])
RAW_COLS = base_cols_ + ['Label', 'Attack_Type'] + \
           [c for i in range(N_B) for c in (f'Pg_ref_{i+1}', f'Qg_ref_{i+1}', f'bus_label_{i+1}')]

# ── 2. AE as numpy weights; must equal Keras ──
dense = [l for l in autoencoder_.layers if l.__class__.__name__ == 'Dense']
AE_LAYERS = [dict(W=l.get_weights()[0], b=l.get_weights()[1], act=l.get_config()['activation']) for l in dense]
assert all(L['act'] in ('relu', 'sigmoid', 'linear') for L in AE_LAYERS), 'unexpected AE activation'
def _ae_np(x):
    for L in AE_LAYERS:
        x = x @ L['W'] + L['b']
        x = np.maximum(x, 0) if L['act'] == 'relu' else (1 / (1 + np.exp(-x)) if L['act'] == 'sigmoid' else x)
    return x
Xs = scaler_ae_.transform(test[ae_cols_].values)
keras_out = autoencoder_.predict(Xs, verbose=0, batch_size=1024)
ae_np_diff = float(np.abs(_ae_np(Xs) - keras_out).max())
assert ae_np_diff < 1e-5, f'numpy AE differs from Keras by {ae_np_diff}'

# ── 3. Check the saved AE and RF reproduce alarm_log (values there are rounded to 3 dp) ──
err = np.mean(np.square(Xs - keras_out), axis=1)
ae_s = np.clip((err - FUSION_['ae_lo']) / (FUSION_['ae_hi'] - FUSION_['ae_lo'] + 1e-9), 0, 1)
rf_s = 1 - rf_model_.predict_proba(test[rf_cols_].values)[:, 0]
d_ae = float(np.abs(ae_s.round(3) - log['ae_score'].values).max())
d_rf = float(np.abs(rf_s.round(3) - log['rf_score'].values).max())
n_ae_off = int((np.abs(ae_s - log['ae_score'].values) > 0.0005 + 1e-9).sum())
n_rf_off = int((np.abs(rf_s - log['rf_score'].values) > 0.0005 + 1e-9).sum())

# ── 3b. Normal reference for the dashboard's measurement table (display only, never used to decide) ──
# From the 5,000 NORMAL snapshots of the development data (seed 42) — not from the test set.
dev = pd.read_csv(f'{SRC}/dev_dataset_raw.csv', usecols=base_cols_ + ['Label'])
devN = dev[dev.Label == 0][base_cols_]
NORMAL_REF = dict(source=f'dev_dataset_raw.csv, {len(devN)} normal snapshots (seed {DEV_SEED})',
                  mean=devN.mean().to_dict(), std=devN.std().to_dict(),
                  p1=devN.quantile(0.01).to_dict(), p99=devN.quantile(0.99).to_dict())

# ── 4. The model file ──
bundle = dict(
    version=2,
    config=CONFIG, raw_cols=RAW_COLS,                                   # CONFIG from cell 3
    ae_layers=AE_LAYERS, scaler_ae=scaler_ae_, ae_feature_cols=ae_cols_,
    ae_threshold=float(ae_json['threshold_mean_plus_2sd']),
    rf_model=rf_model_, rf_feature_cols=rf_cols_,
    rf_loc=rf_loc_, loc_threshold=float(loc_cfg['single_threshold']),
    neighbors=loc_cfg['neighbors'], neighbors_2=loc_cfg['second_order_neighbors'],
    physics=dict(baseline_va=P['baseline_va'], baseline_vm=P['baseline_vm'],
                 P_mu=P['P_mu'], P_sig=P['P_sig'], Q_mu=P['Q_mu'], Q_sig=P['Q_sig'],
                 Vad_mu=P['Vad_mu'], Vad_sig=P['Vad_sig'], Vmd_mu=P['Vmd_mu'], Vmd_sig=P['Vmd_sig'],
                 Z=float(P['Z_FINAL']), score_final=int(P['SCORE_FINAL']), n_checks=int(P['N_CHECKS']),
                 use_s_loading=bool(P['USE_S_LOADING']), thr_S=float(P['thr_S']), check_names=check_names_),
    fusion=FUSION_, normal_reference=NORMAL_REF,
    sklearn_version=sklearn.__version__, numpy_version=np.__version__,
)
joblib.dump(bundle, f'{BUNDLE}/griddefense_model.joblib', compress=3)

# ── 5. Test set + the notebook's own Section 10 decisions (reference for the app) ──
t = test[RAW_COLS].copy()
t['nb_alarm'] = log['alarm'].astype(int).values
t['nb_fusion'] = log['fusion_score'].values
t['nb_ae'] = log['ae_score'].values
t['nb_rf'] = log['rf_score'].values
t['nb_phys'] = log['physics_score'].values
t['nb_rf_type'] = log['rf_type'].values
t['nb_named_buses'] = log['named_buses'].astype(str).values          # e.g. "4 9" ; "" = none
t.to_csv(f'{BUNDLE}/test_snapshots.csv.gz', index=False, compression='gzip')

# ── 6. Saved result tables for the "Research results" page (copied unchanged) ──
copied = []
for p in sorted(glob.glob(f'{SRC}/results/*.csv') + glob.glob(f'{SRC}/results/*.json')):
    shutil.copy(p, f'{BUNDLE}/results/{os.path.basename(p)}'); copied.append(os.path.basename(p))
    SRC_MD5[f'results/{os.path.basename(p)}'] = _md5(p)        # lets the app prove each table is unchanged

# ── 7. Manifest + fingerprint ──
try:
    import tensorflow as _tf; tf_v = _tf.__version__
except Exception:
    tf_v = None
manifest = dict(
    bundle_format=2,
    provenance=globals().get('BUNDLE_PROVENANCE', 'notebook'),   # 'notebook' unless a developer overrides it
    exported_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
    source_folder=SRC,
    model_sha256=hashlib.sha256(open(f'{BUNDLE}/griddefense_model.joblib', 'rb').read()).hexdigest(),
    test_snapshots_sha256=hashlib.sha256(open(f'{BUNDLE}/test_snapshots.csv.gz', 'rb').read()).hexdigest(),
    versions=dict(python=platform.python_version(), sklearn=sklearn.__version__, numpy=np.__version__,
                  pandas=pd.__version__, tensorflow=tf_v, joblib=joblib.__version__),
    source_md5=SRC_MD5,
    features=dict(ae=len(ae_cols_), rf=len(rf_cols_), localiser=172, physics_checks=check_names_),
    thresholds=dict(ae=bundle['ae_threshold'], fusion=FUSION_['threshold'], w_ae=FUSION_['w_ae'],
                    w_rf=FUSION_['w_rf'], w_phys=FUSION_['w_phys'], ae_lo=FUSION_['ae_lo'], ae_hi=FUSION_['ae_hi'],
                    physics_z=bundle['physics']['Z'], physics_votes=bundle['physics']['score_final'],
                    localiser=bundle['loc_threshold']),
    test_set=dict(seed=int(TEST_SEED), snapshots=int(len(t)), normal=int((t.Label == 0).sum()),
                  attacked=int((t.Label == 1).sum()), notebook_alarms=int(t.nb_alarm.sum())),
    colab_checks=dict(ae_numpy_vs_keras_max_diff=ae_np_diff,
                      ae_score_vs_alarm_log_max_diff_3dp=d_ae, ae_score_rows_off=n_ae_off,
                      rf_score_vs_alarm_log_max_diff_3dp=d_rf, rf_score_rows_off=n_rf_off),
    results_copied=copied,
)
json.dump(manifest, open(f'{BUNDLE}/bundle_manifest.json', 'w'), indent=2, default=float)

sz = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(BUNDLE) for f in fs) / 1e6
print(f"✓ AE numpy vs Keras: max difference {ae_np_diff:.2e} on {len(Xs)} snapshots")
print(f"{'✓' if n_ae_off == 0 else '✗'} AE score vs alarm_log: {n_ae_off} of {len(t)} rows differ beyond rounding")
print(f"{'✓' if n_rf_off == 0 else '✗'} RF score vs alarm_log: {n_rf_off} of {len(t)} rows differ beyond rounding")
print(f"✓ Bundle written to {BUNDLE} ({sz:.0f} MB): model, {len(t)} test snapshots "
      f"({int(t.nb_alarm.sum())} notebook alarms), {len(copied)} result files")
print(f"  fingerprint {manifest['model_sha256'][:12]} · scikit-learn {sklearn.__version__} · numpy {np.__version__}")

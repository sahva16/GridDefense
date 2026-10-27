"""The three learned parts: autoencoder (Section 5), Random Forest (Section 6), localiser (Section 7)."""
import random

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.preprocessing import MinMaxScaler

from . import config as C
from .features import add_topo_features


# ── Autoencoder ─────────────────────────────────────────────────────
def _build_ae(seed, n_in=56):
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    keras.backend.clear_session()
    random.seed(seed); np.random.seed(seed); tf.random.set_seed(seed)
    inp = keras.Input(shape=(n_in,))
    x = inp
    for units in C.AE_LAYERS:
        x = layers.Dense(units, activation="relu")(x)
    out = layers.Dense(n_in, activation="sigmoid")(x)
    model = keras.Model(inp, out, name="AE_GridDefense")
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=C.AE_LR), loss="mse")
    return model


def _fit_ae(model, X_tr, X_va):
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    hist = model.fit(X_tr, X_tr, validation_data=(X_va, X_va), epochs=C.AE_EPOCHS, batch_size=C.AE_BATCH,
                     callbacks=[EarlyStopping(monitor="val_loss", patience=15, restore_best_weights=True),
                                ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=7, min_lr=1e-6)],
                     verbose=0)
    return min(hist.history["val_loss"])


class AutoencoderDetector:
    """Trained on normal training snapshots only (56 raw measurements, scaled 0–1).
    Alarm when the reconstruction error exceeds the validation-normal mean + 2 SD."""

    def fit(self, train_normal_X, val_normal_X, seeds=C.AE_SEEDS, verbose=True):
        self.scaler = MinMaxScaler().fit(train_normal_X)
        X_tr, X_va = self.scaler.transform(train_normal_X), self.scaler.transform(val_normal_X)
        self.seed_val_loss = {}
        for s in seeds:                                   # seed chosen on validation loss only
            self.seed_val_loss[s] = _fit_ae(_build_ae(s, X_tr.shape[1]), X_tr, X_va)
            if verbose:
                print(f"    AE seed {s}: val_loss {self.seed_val_loss[s]:.6f}")
        self.seed = min(self.seed_val_loss, key=self.seed_val_loss.get)
        self.model = _build_ae(self.seed, X_tr.shape[1])
        _fit_ae(self.model, X_tr, X_va)
        err = self._err_scaled(X_va)
        self.threshold = float(err.mean() + 2 * err.std())
        return self

    def _err_scaled(self, Xs):
        return np.mean(np.square(Xs - self.model.predict(Xs, verbose=0)), axis=1)

    def error(self, X):
        return self._err_scaled(self.scaler.transform(X))

    def set_score_bounds(self, val_err, val_is_normal):
        """0–1 score bounds for fusion, from VALIDATION data (normal mean − 2 SD … validation max)."""
        self.lo = float(val_err[val_is_normal].mean() - 2 * val_err[val_is_normal].std())
        self.hi = float(val_err.max())

    def score(self, err):
        return np.clip((err - self.lo) / (self.hi - self.lo + 1e-9), 0, 1)


# ── Random Forest (attack type) ─────────────────────────────────────
def train_rf(X_train, y_type):
    rf = RandomForestClassifier(**C.RF_PARAMS).fit(X_train, y_type)
    assert list(rf.classes_) == [0, 1, 2, 3]
    return rf


# ── Localiser (one RF per bus, 172 features) ────────────────────────
class Localiser:
    def fit(self, X_train_104, y_bus_train, X_val_104, y_bus_val, y_type_val):
        self.model = MultiOutputClassifier(RandomForestClassifier(**C.LOC_PARAMS), n_jobs=1)
        self.model.fit(add_topo_features(X_train_104), y_bus_train)     # all training snapshots, normals included
        P = self.probas(X_val_104)
        normal, attacked = (y_type_val == 0), (y_type_val != 0)
        best = (-1.0, None, None)
        for th in C.LOC_THRESHOLD_GRID:                                  # best validation exact match,
            yp = (P >= th).astype(int)                                   # ≤ 5 % false localisation on normals
            fl = np.mean(np.any(yp[normal] == 1, axis=1))
            if fl > C.FALSE_LOC_LIMIT:
                continue
            ex = np.mean(np.all(yp[attacked] == y_bus_val[attacked], axis=1))
            if ex > best[0]:
                best = (ex, th, fl)
        assert best[1] is not None, "no threshold met the validation false-localisation limit"
        self.val_exact, self.threshold, self.val_false_loc = best
        return self

    def probas(self, X_104):
        X = add_topo_features(X_104)
        cols = []
        for est in self.model.estimators_:
            pos = np.where(est.classes_ == 1)[0]
            cols.append(np.zeros(len(X)) if len(pos) == 0 else est.predict_proba(X)[:, pos[0]])
        return np.column_stack(cols)

    def predict(self, X_104):
        return (self.probas(X_104) >= self.threshold).astype(int)

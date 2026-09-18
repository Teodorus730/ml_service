import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer


class DateFeatureExtractor(BaseEstimator, TransformerMixin):
    def __init__(self, date_cols=None):
        self.date_cols = date_cols

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        if isinstance(X, pd.DataFrame):
            X_out = X.copy()
        else:
            X_out = pd.DataFrame(X, columns=self.date_cols)

        for col in X_out.columns:
            dt_series = pd.to_datetime(X_out[col], errors="coerce")

            X_out[f"{col}_year"] = dt_series.dt.year
            X_out[f"{col}_month"] = dt_series.dt.month
            X_out[f"{col}_day"] = dt_series.dt.day
            X_out[f"{col}_dayofweek"] = dt_series.dt.dayofweek

            X_out = X_out.drop(columns=[col])

        return X_out


class SqueezedTfidfVectorizer(TfidfVectorizer):
    def fit(self, X, y=None):
        return super().fit(X.ravel(), y)

    def fit_transform(self, X, y=None):
        return super().fit_transform(X.ravel(), y)

    def transform(self, X):
        return super().transform(X.ravel())
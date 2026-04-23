class FrostGuardKNNAdapter:
    """Compatibility shim for the saved frostguard_knn.joblib artifact."""

    def predict(self, X):
        return self.pipeline.predict(X)

    def predict_proba(self, X):
        if hasattr(self.pipeline, "predict_proba"):
            return self.pipeline.predict_proba(X)
        return None

    def kneighbors(self, X, n_neighbors=None, return_distance=True):
        model = getattr(self, "pipeline", self)
        if hasattr(model, "kneighbors"):
            return model.kneighbors(X, n_neighbors=n_neighbors, return_distance=return_distance)
        if hasattr(model, "named_steps"):
            for _, step in reversed(model.steps):
                if hasattr(step, "kneighbors"):
                    return step.kneighbors(X, n_neighbors=n_neighbors, return_distance=return_distance)
        raise AttributeError("KNN artifact does not expose kneighbors().")

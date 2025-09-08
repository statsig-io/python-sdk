from typing import Optional

class EvaluationContext:
    """
    Context object that holds optional evaluation parameters that need to be passed
    down through the evaluation function chain.
    """

    def __init__(self,
                 sampling_rate: Optional[float] = None,
                 client_key: Optional[str] = None,
                 target_app_id: Optional[str] = None):
        self.sampling_rate = sampling_rate
        self.client_key = client_key
        self.target_app_id = target_app_id

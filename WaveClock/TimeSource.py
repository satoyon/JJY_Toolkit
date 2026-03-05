
class TimeSource:
    """時刻ソースのインターフェースを定義する基底クラス"""
    def add_callback(self, callback):
        raise NotImplementedError("Subclasses must implement add_callback()")


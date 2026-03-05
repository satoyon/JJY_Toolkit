class TimeSyncer:
    """時刻ハードウェアインターフェースを定義する基底クラス"""
    def sync_start(self):
        """時刻同期開始要求"""
        raise NotImplementedError("Subclasses must implement sync_start()")

    def sync_stop(self):
        """時刻同期停止要求"""
        raise NotImplementedError("Subclasses must implement sync_stop()")

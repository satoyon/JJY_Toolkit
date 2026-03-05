class Debug():
    """
    デバッグメッセージ用のクラス
    """
    DEBUG_ENABLED = True

    def dprint(self, *args):
        """
        [クラス名] メッセージ の形式でデバッグ出力

        Args:
            *args: 出力したいメッセージや変数。
        """
        if self.DEBUG_ENABLED:
            print(f"[{self.__class__.__name__}]", *args)

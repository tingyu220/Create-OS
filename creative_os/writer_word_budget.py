"""Writer 整章字数契约与软提示；不截断正文、不门禁、不调用模型。"""

from dataclasses import dataclass


def count_writer_words(content: str) -> int:
    """沿用现有口径：统计非空白字符，包含标题与标点。"""
    return len("".join(content.split()))


@dataclass(frozen=True, slots=True)
class WriterWordBudget:
    target_words: int
    tolerance_words: int
    input_words: int

    @property
    def min_words(self) -> int:
        return max(1, self.target_words - self.tolerance_words)

    @property
    def max_words(self) -> int:
        return self.target_words + self.tolerance_words

    def prompt(self, *, formal_words: int, mode: str) -> str:
        contract = (
            f"最终整章总字数目标：{self.target_words} 字，允许误差：±{self.tolerance_words} 字，范围：{self.min_words}-{self.max_words} 字。"
            "这是最终完整章节的总量，不是本次新增字数；统计非空白字符，包含标题和标点。"
            f"当前正式稿精确字数：{formal_words} 字；本次冻结输入精确字数：{self.input_words} 字，实际预算以本次输入为准。"
            f"若保留已有内容，目标新增预算：{max(0, self.target_words - self.input_words)} 字，"
            f"新增上限预算：{max(0, self.max_words - self.input_words)} 字。"
        )
        if mode == "analyze":
            return contract + "以上仅供分析；本次不改写、不续写正文。"
        if self.input_words > self.max_words:
            contract += (
                f"当前输入已比整章上限多 {self.input_words - self.max_words} 字，不能在原稿后再追加目标篇幅。"
                "本次应整合、压缩已有内容，保留关键剧情、人物动机与因果；如需推进情节，应通过替换冗余内容腾出篇幅。"
            )
        elif self.input_words >= self.target_words:
            contract += "当前输入已达到整章目标，应以整合改写和必要收束为主，避免继续扩写大量新情节。"
        elif self.input_words:
            contract += "续写时在剩余预算内接续情节并整合已有正文；改写时重组现有正文，总量仍是上述整章目标。"
        else:
            contract += "本章输入为空，本次生成一章完整新正文，总量仍是上述整章目标。"
        return contract + (
            "只输出最终完整章节，不要完整照抄原稿后再新增一份目标篇幅，也不要只输出新增片段。"
            "字数是软约束，允许为叙事质量少量偏离；不要机械截断、堆砌或重复内容。"
        )

    def assess(self, content: str) -> dict:
        actual = count_writer_words(content)
        within = self.min_words <= actual <= self.max_words
        significant = not within and (actual * 2 > self.target_words * 3 or actual * 2 < self.target_words)
        severity = "within_range" if within else ("significant" if significant else "outside_range")
        change = actual - self.input_words
        message = f"整章总量 {actual} 字，目标 {self.min_words}–{self.max_words} 字，冻结输入 {self.input_words} 字，净变化 {change:+d} 字"
        message += "，字数在目标范围内" if within else ("，字数超出目标范围" if actual > self.max_words else "，字数低于目标范围")
        if significant:
            message += "，显著偏离目标"
        options = []
        if significant:
            adjustment = "压缩" if actual > self.max_words else "补足"
            options = [
                "可保留当前候选，由作者决定是否采用",
                f"可在“继续修改”中选择候选或原稿，明确要求整合{adjustment}至 {self.min_words}–{self.max_words} 字；确认后才执行",
            ]
        return {"target_scope": "chapter_total", "count_method": "non_whitespace_characters",
                "target_words": self.target_words, "min_words": self.min_words, "max_words": self.max_words,
                "input_words": self.input_words, "actual_words": actual, "net_change_words": change,
                "within_word_range": within, "severity": severity, "message": message,
                "adjustment_options": options}

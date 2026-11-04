import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.typography import validate_text


POLICY = {"conditional_period_types": ["system_message", "item_description"], "terminal_period": "。",
          "internal_punctuation": "，、；：？！…—（）「」『』“”‘’《》【】,;:?!()[]\"。",
          "alternative_endings": "？！?!…"}


class TypographyTests(unittest.TestCase):
    def test_plain_system_sentence_omits_period(self):
        validate_text("门已经打开", "system_message", POLICY)
        with self.assertRaisesRegex(ValueError, "omit"):
            validate_text("门已经打开。", "system_message", POLICY)

    def test_mid_sentence_punctuation_keeps_period(self):
        validate_text("记忆卡已满，请更换记忆卡。", "system_message", POLICY)
        with self.assertRaisesRegex(ValueError, "keep"):
            validate_text("记忆卡已满，请更换记忆卡", "system_message", POLICY)

    def test_item_description(self):
        validate_text("恢复少量生命值", "item_description", POLICY)
        validate_text("恢复生命值，并解除中毒。", "item_description", POLICY)

    def test_dialogue_and_cutscenes_are_normal_prose(self):
        validate_text("这还是头一回。", "dialogue", POLICY)
        validate_text("一切都结束了。", "cutscene", POLICY)

    def test_placeholders_and_engine_tags_are_not_punctuation(self):
        validate_text("获得了%s", "system_message", POLICY)
        validate_text("按<O>打开道具栏", "system_message", POLICY)
        with self.assertRaisesRegex(ValueError, "omit"):
            validate_text("获得了%s。", "system_message", POLICY)

    def test_question_exclamation_and_labels_unchanged(self):
        for text in ("是否使用？", "记忆卡已满！", "现在要离开吗？"):
            validate_text(text, "system_message", POLICY)
        validate_text("生命值：%d", "ui_label", POLICY)


if __name__ == "__main__":
    unittest.main()

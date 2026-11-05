import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mysticnights.typography import validate_text, normalize_parenthetical_periods


POLICY = {"conditional_period_types": ["system_message", "item_description"], "terminal_period": "。",
          "internal_punctuation": "，、；：？！…—（）「」『』“”‘’《》【】,;:?!()[]\"。",
          "alternative_endings": "？！?!…"}


class TypographyTests(unittest.TestCase):
    def test_explicit_breaks_cannot_start_with_closing_punctuation(self):
        policy = {**POLICY, 'no_line_start': '，。！？、）…—,.;!?%'}
        for bad in ('正文<BR>。', '正文<BR>，下文', '正文\n……错误'):
            with self.assertRaisesRegex(ValueError, 'line start'):
                validate_text(bad, 'document', policy)
        for good in ('正文<BR>下文。', '网络错误(%d)<BR>%s', '正文<BR><BR>下文'):
            validate_text(good, 'document', policy)

    def test_parenthetical_single_sentences_follow_policy_in_all_text_types(self):
        policy = {**POLICY, 'conditional_parentheticals': True,
                  'enclosure_pairs': [['（', '）'], ['(', ')']]}
        for text_type in ('system_message', 'dialogue', 'item_description', 'cutscene'):
            for bad, good in [('（锁着。）', '（锁着）'), ('(门好像锁着。)', '(门好像锁着)'),
                              ('她走了。（门锁着。）', '她走了。（门锁着）')]:
                self.assertEqual(normalize_parenthetical_periods(bad, policy), good)
                with self.assertRaisesRegex(ValueError, 'Parenthetical'):
                    validate_text(bad, text_type, policy)
                if text_type in ('dialogue', 'cutscene') or good in ('（锁着）', '(门好像锁着)'):
                    validate_text(good, text_type, policy)
        for good in ('（锁着，打不开。）', '（按<O>打开）', '(PS2)', '（现在离开吗？）'):
            self.assertEqual(normalize_parenthetical_periods(good, policy), good)
            validate_text(good, 'dialogue', policy)

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

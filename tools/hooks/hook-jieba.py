# Replaces pyinstaller-hooks-contrib's hook for jieba, which adds all of
# jieba's data (its dictionary, keyword and part-of-speech tables and a
# paddle model: over 30 MB). KaiDrop uses only jieba's code and its own
# word list (kaidrop/data/words-zh.xz), so nothing is added here.
datas = []

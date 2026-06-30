import re

with open("config.py", "r") as f:
    content = f.read()

content = re.sub(r'"momentum_min_volume_ratio":\s*0\.75', '"momentum_min_volume_ratio": CRYPTO_MOMENTUM_MIN_VOLUME_RATIO', content)
content = re.sub(r'"grade_a_min_volume_ratio":\s*1\.10', '"grade_a_min_volume_ratio": CRYPTO_GRADE_A_MIN_VOLUME_RATIO', content)
content = re.sub(r'"grade_b_min_volume_ratio":\s*0\.75', '"grade_b_min_volume_ratio": CRYPTO_GRADE_B_MIN_VOLUME_RATIO', content)
content = re.sub(r'"trend_continuation_min_volume_ratio":\s*0\.75', '"trend_continuation_min_volume_ratio": VOLUME_MIN_RATIO', content)

with open("config.py", "w") as f:
    f.write(content)

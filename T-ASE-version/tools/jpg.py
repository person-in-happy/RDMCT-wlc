from pathlib import Path
from PIL import Image
for p in Path('T-ASE-version/output/qa').glob('contact-*.png'):
 im=Image.open(p);im.thumbnail((1056,960));im.convert('RGB').save(p.with_suffix('.jpg'),quality=45,optimize=True)


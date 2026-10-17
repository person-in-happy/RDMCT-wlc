"""Material paths. An AL visit by an accompanying dummy is not alignment."""
from dataclasses import dataclass

@dataclass(frozen=True)
class MaterialSourceConfig:
    dual_source: bool

    def product_route(self, load_port, chamber):
        origin=self._lp(load_port)
        return (origin,'ATR','AL','ATR','LLupper','VTR',f'CH{chamber}',
                'VTR','LLlower','ATR',origin)

    def dummy_route(self, chamber, *, load_port=None, atmospheric_storage=None,
                    vacuum_storage=None, accompany_product=False):
        if self.dual_source:
            if load_port is not None or atmospheric_storage or not vacuum_storage or accompany_product:
                raise ValueError('Dual-source dummies require vacuum storage and cannot accompany an atmospheric AL visit')
            return (vacuum_storage,'VTR',f'CH{chamber}','VTR',vacuum_storage)
        if vacuum_storage is not None or (load_port is not None and atmospheric_storage):
            raise ValueError('Specify one atmospheric dummy origin')
        origin=atmospheric_storage or (self._lp(load_port) if load_port is not None else None)
        if not origin:raise ValueError('Specify atmospheric dummy storage beside LP4')
        entry=(origin,'ATR','AL vicinity (held on ATR)','ATR') if accompany_product else (origin,'ATR')
        return entry+('LLupper','VTR',f'CH{chamber}','VTR','LLlower','ATR',origin)

    @staticmethod
    def _lp(load_port):
        if load_port not in (1,2,3,4):raise ValueError('Specify LP1--LP4')
        return f'LP{load_port}'

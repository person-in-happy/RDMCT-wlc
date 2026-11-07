"""Distinguish an exported subset count from a constructive space lower bound."""
import math


def filename(n,count,simple):
    kind='简化取放' if simple else '详细动作'
    return f'{n}wafer-已列{count}种_每配置至少{math.factorial(n)}种_{kind}.txt'


def heading(n,count,simple):
    kind='简化取放序列' if simple else '完整动作顺序'
    return (f'{n}片产品晶圆：本文件已列出{count:,}种不同{kind}；'
            f'每个固定配置的可行顺序总数至少为{n}! = {math.factorial(n):,}种。'
            '这是已证明下界，不是总数估计；精确总数尚未求得。\n')

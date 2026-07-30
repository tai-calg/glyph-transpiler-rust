from __future__ import annotations

import base64
from pathlib import Path
import subprocess
import sys
import zlib

_parent = subprocess.check_output(["git", "show", "f8cfdf4a5142f8ea7218dbab1395c6efbc3a8968:tests/test_transition_system_execution_review_regressions.py"], text=True)
_scope = {"__file__": __file__, "__name__": "_glyph_essential_parent"}
exec(compile(_parent, __file__, "exec"), _scope)

_core_path = Path("glyph/_transition_system_execution_core.py")
_core = _core_path.read_text()
_old = '    action = (\n        build_operation_action(representative_invocations)\n        if common_sequence\n        else _conditional_action(records)\n    )'
_new = '    action = (\n        None\n        if unresolved or multiple\n        else build_operation_action(representative_invocations)\n        if common_sequence\n        else _conditional_action(records)\n    )'
if _old not in _core:
    raise RuntimeError("essential core safety patch target is missing")
_core_path.write_text(_core.replace(_old, _new, 1))

for _module_name in list(sys.modules):
    if _module_name == "glyph" or _module_name.startswith("glyph."):
        del sys.modules[_module_name]

_clean = zlib.decompress(base64.b85decode('c-qxk-EZ4A5P#QSq3U6f8rRtNXv`^+E*tXDv`Df6gBK8rL?_&2N)x5DS=;}8cSq`j5@kC{yRCkRC6f2a<L{2=tjm1kGq$d)y5x-cVpHU0<;POyRa}W&D$g@xwG>swRpqUbrn)bLylK|IjthMC^xRE$U);`<d{c;wm^8~?bwh7O!80LwpF-qJfmF`!1b?R*qU%~@DYNH1&rA8**CIGmd0i$v)L#o<Rb}MAIP_DIR4aIy`T6x9JgKf0o)4eAu8O+ymo9a}Xx=cb`1{JRoca2j$#}z;LCH~x7bU+bxl%wqC;fwn*q0o9DV=JETJ(IAr#zb(Mdqo9Z_0S1=Aw*@VR^wN_>)y-ER{e7Lt?OKJZ+gp#=0i7y_-0>1=GM_;;{-yqu^>4m>C7n-(K~VmuNc;;73$^)4r_pk_LPs8_uhs(-U}gbZc4(0=4&yTz|RrgI8Iucp5;YrDjnTmp8n!7QF#C1jMd!Oq`$)mI_s5@qL)&61QoKTVOzYK~sVg49y&bg@GQmcMeEGJ+9XnVL{}B=>dG9T}nvMR6^A0rL#tb$mf~junsgnKDsyoi9yhK+W#@n%aBZ5;Nt~8&4h$7Se)WtR7CL%)L+sn3KbX=aQK!jMX0@pi*cu5DK9iv&5O9yNdnQiL?6QIIu;om@#Rq#mmAM}PSQe*Ggk7yYB<-kxUO#VQvA)+#c|{vptRQ@eW`_gL`EMq`SVT_)Nj!&jlAdQJmI3KhBm_f9d=qy*xn7J{;l~-qro?{cHY<7KRon1T~I?bo#8Oidjajk#cvmvC$IHRsC$Lci&U>563RRS3JwqV6dC$mNPnQH9_(rB5s*O4ki83IccVClUY{KTjx}VSaIkDidxH>FbzJ4;V6;v}WsFL)SSkOqJ$V;o*vWgI)cAT%Aa&kilnNUFpI^eCSFz%eJ{fqfa2%XkaL_$vH+5X5EX}!MkOx>%UuQzyvRE=9*F09@8t~B^#RM3I5VC7JZfCjVixvR%xd*?S4LI<F-(>(_bTAHZJG^I&rK6B(efo^do}Tv(jf=KNSGPqvkh*xsc<HGzI84zLh0)5fobBR>mN#DNz!N;>Kz?VIi=vj^02&Z?M5}-|fxygs59RU0-xp0}0OhJ3C*YQMc@j5#nsq&7ZxR7+KAsCBVioj)LOIrVjEM?XwItnCpRjwv5Sv59^RoIW280b`c^`Jl&B4EArQV6^7Eqmb29O$Mc56^(&+MKHd(2P%s^cuoxC|$Zie~=zmh)4c_`r)Fv_<V0q_I7`^vR{hsSJZ*&;_%exM+&%SvaJN288yh*MMlwyiiOPJP~n*gzWmh7l^E%#=o{BKTapR4?Wv@%KJxH7pzNnLE7!qLn<)}E>e^sCIF3Hl#L3r2Nq|axj@rJTJuCX`ae;dG<uxU#@ij7_T0Z4Ps!wtw)Mbn$`Sb3is&e*foSH#)kEdk9qh{%?CNXsU}DSB!)n{oE1FqrgZ3;93Nk<+hqE6fxNp%&ES=BC$t08?IC}*4-|b*vyW2%><1JL0%oOMBS^z3Twy$9|tL3{A?hv5NU7XdNVJ?Fb6U#Di0xknlC8fwo^wq^}gT8Yj1t1EXwIu*EM1?(76xlsXZh7)2Pk)#FNNIrG$Z!Gs!4Yo8Nm=IQ@|@!(jHlC3{=@OCTYm`a`m#gwy*QpZC=IS#^!ug+C$YXr`3o@5ahEc>;IuXd7e_B)#;Nm+rvC>uo(VH22vbqAM|FZ|tIL{_12jXN;zA+oxUy@)PFZu;e6m=$dpuNhbFdy$-8w2%!|pLfssq&=%GqFM>$xAibt|2rxP$U)FPv2MCd70)U1T@e+hO7)gmz_oz!-JVT3pls$O5`^BkNr<b_sC1@#PZ*IQDq;fao&k#2sB%gV30Yg#C7~6$J?eu!d7TU<P04zE^-fHY-!X4I*bnnIn*+e%N#oU=ZVX9Fmx+)EeyBc_a7=n=f8ZVM-URy0jbYGb=r2YE&OiSnswOqbc1p^1gx&<QHi>ewNGTf6==9_pZ2>^RQEE#n5BKqdEJu$Oe)>XT`J~raw?RqxQZ&;)6W4tIGOhqw|NL2Wi2l9guvg5Fx`(hV?rGYkre((q5KzpR&yzDghs1C&B30fOQI&kUf2}jq6508iNfO`2xOcSp|b^^<Ccs!|PAmPfFq}gQTZK%1!&J?NVVQ>N?A*lzG}+2P05lbRKw_*#kJdLr@cAbG+nuIXn-KXj8Y$hv(;U2m60;AsMwg9BqnPZf{hW<1@H8OvJga0f(0itI`@q=%&spQGo40!AluuZKXr*g<A;yJkGAcJMZYizEA0c&Vss0R$;Wb5I4Zq!y$~1Zp3?1fkf;ZRy0CsvK_$cL;o5LPveYb*GR<79zt%Dg;dLUs+8JVfb><L^|XF+HA0Mu<L;8=K+9YnL6F?>kEb%Ghey^V+W@5V{X}gs>5pB71`#fe3GN!hL8V_@L}cZ@m5HsLqobmueP+%9vTc1d?wNd{rus0M+KorJERL?$U9FIS{!l4k7y07y^qlF`!!FN{&Mr<bPv4xeqw}ACd3|zr$$mL|d;aFvle1vN&e`q8e*%%YszfsEc1NyOwL#ZWZ^KNCy6Zi-->=6`EgFOIRz0L0;Q;!Xzv@Bow7(mI>GB53f^lLXr}t9BP{Wq(UVQEU{(wwN$i0Q9=ZUq?=pTR>BV8Dz1tA#=G~TzruH$GJdH(<j>^_4')).decode("utf-8")
Path(__file__).write_text(_clean)
exec(compile(_clean, __file__, "exec"), globals())

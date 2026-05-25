1. In einem Datei nur ein Objekt (Part, Assambly, Halbzeug)
1. Pattern Objekte: Part, Body, Assembly, Link, oder Elemente mit Shape.
1. Beim suchen links fü Joints sind nur erste LCS zulässig, es wird weiter nicht gesucht.
Es wird erstes Outlink genommen der fängt mit Name *Origin* an. [AssemblyPatternCreator.py](https://github.com/maxx04/FreeCAD-Development/blob/35b256950090684d51b83570b71c7d6eb401997b/FCProject/AssemblyPatternCreator.py#L446)
1.
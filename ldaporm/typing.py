from typing import Dict, List, Tuple, Union

ModifyDeleteModList = List[Union[Tuple[int, str, str], Tuple[int, str]]]
AddModlist = List[Tuple[str, str]]
LDAPData = Tuple(str, Dict[str, List[str]])

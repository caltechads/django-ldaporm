from typing import Dict, List, Tuple, Union

DeleteModListEntry = Tuple[int, str, None]
ModifyModListEntry = Tuple[int, str, str]
AddModlistEntry = Tuple[str, str]
ModifyDeleteModList = List[Union[DeleteModListEntry, ModifyModListEntry, AddModlistEntry]]
AddModlist = List[Tuple[str, str]]
LDAPData = Tuple[str, Dict[str, List[bytes]]]

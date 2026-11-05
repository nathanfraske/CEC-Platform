"""Restore an explicitly scoped temporary copper prefix between attempts."""
import pcbnew
from cec_native_items import discard_items


class CopperSnapshot:
    def __init__(self, board, uuids):
        self.board=board
        self.uuids=set(uuids)
        self.items={item.m_Uuid.AsString():item.Duplicate()
                    for item in board.GetTracks() if item.m_Uuid.AsString() in self.uuids}
        if set(self.items)!=self.uuids or any(item is None for item in self.items.values()):
            raise ValueError('cannot snapshot complete temporary copper scope')
        self.groups={group.m_Uuid.AsString():
            {item.m_Uuid.AsString() for item in group.GetItems()} & self.uuids
            for group in board.Groups()}
        self.groups={identifier:members for identifier,members in self.groups.items() if members}

    def restore(self):
        groups={group.m_Uuid.AsString():group for group in self.board.Groups()}
        if not set(self.groups)<=set(groups):
            raise ValueError('temporary copper parent group is missing')
        restored=[]
        for identifier,prototype in self.items.items():
            item=prototype.Duplicate()
            if item is None:
                raise ValueError('cannot restore temporary copper')
            item.m_Uuid.Clone(pcbnew.KIID(identifier))
            restored.append(item)
        # Only these transaction-created parent items are replaceable. Source
        # power, prior pairs and unrelated return vias are never in this scope.
        discard_items(self.board,[item for item in self.board.GetTracks()
                                  if item.m_Uuid.AsString() in self.uuids])
        for item in restored:
            self.board.Add(item)
            for identifier,members in self.groups.items():
                if item.m_Uuid.AsString() in members:
                    groups[identifier].AddItem(item)

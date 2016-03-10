from collections import Mapping, MutableMapping
from sortedcontainers import SortedDict
import queue as q

class Tree(MutableMapping):
    def __init__(self, max_size=1024):
        self.root = self._create_leaf(tree=self)
        self.max_size = max_size

    @staticmethod
    def _create_leaf(*args, **kwargs):
        return LazyNode(node=Leaf(tree=kwargs.get('tree')), tree=kwargs.get('tree'))

    @staticmethod
    def _create_node(*args, **kwargs):
        return Node(*args, **kwargs)

    def _create_root(self, lhs, rhs):
        root = self._create_node(tree=self)
        root.rest = lhs
        root.bucket[min(rhs.bucket)] = rhs

        return root

    def _commit(self):
        self.root._commit()

    def __getitem__(self, key):
        return self.root[key]

    def __setitem__(self, key, value):
        """
        Inserts the key and value into the root node. If the node has been
        split, creates a new root node with pointers to this node and the new
        node that resulted from splitting.
        """
        result = self.root._insert(key, value)

        if result is None:
            return

        key, value = result
        root = Node(self, True)
        root.rest = self.root
        root.bucket[key] = value
        self.root = root

    def __delitem__(self, key):
        raise NotImplementedError

    def __iter__(self):
        return len(self.root)

    def __len__(self):
        for key in self.root:
            yield key

class BaseNode(object):
    def __init__(self, tree, changed=False):
        self.tree = tree
        self.bucket = SortedDict()
        self.changed = changed

    def _insert(self, key, value):
        """
        Inserts the key and value into the bucket. If the bucket has become too
        large, the node will be split into two nodes.
        """

        self.bucket[key] = value
        self.changed = True

        if len(self.bucket) < self.tree.max_size:
            return None

        return self._split()

    def _commit(self):
        pass

class Node(BaseNode):
    def __init__(self, *args, **kwargs):
        self.rest = None

        super().__init__(*args, **kwargs)

    def _select(self, key):
        """
        Selects the bucket the key should belong to.
        """

        # If the key is smaller than the min or larger than the max, immediately return.
        if key < min(self.bucket):
            return self.rest

        elif key >= max(self.bucket):
            return self.bucket.values()[-1]

        # Else find the correct node
        for k, v in reversed(list(self.bucket.items())):
            if k <= key:
                return v

        return self.rest

    def _insert(self, key, value):
        """
        Recursively inserts the key and value by selecting the bucket the key
        should belong to, and inserting the key and value into that back. If the
        node has been split, it inserts the key of the newly created node into
        the bucket of this node.
        """

        result = self._select(key)._insert(key, value)
        self.changed = True

        if result is None:
            return

        key, other = result
        return super()._insert(key, other)

    def _split(self):
        other = LazyNode(node=Node(tree=self.tree, changed=True),
            tree=self.tree)
        #other = Node(self.tree)

        values = self.bucket.items()
        self.bucket = SortedDict(values[:len(values) // 2])
        other.bucket = SortedDict(values[len(values) // 2:])

        key, value = other.bucket.popitem(last=False)
        other.rest = value

        return (key, other)

    def _commit(self):
        self.rest._commit()

        for child in self.bucket.values():
            child._commit()

        #data = packb({
        #    'rest': self.rest.offset,
        #    'values': {k: v.offsett for k, v in self.values.items()}
        #})

        pass

    def __getitem__(self, key):
        return self._select(key)[key]

    def __len__(self):

        print(len(self.rest))
        print (self.bucket.values())

        #len(value) for child in self.bucket.values() + len(self.rest)


        return sum([len(child) for child in self.bucket.values()]) + len(self.rest)

    def __iter__(self):
        for key in self.rest:
            yield key

        for child in self.bucket.values():
            for key in child:
                yield key


class Leaf(BaseNode, Mapping):
    def _split(self):
        other = LazyNode(node=Leaf(tree=self.tree, changed=True),
            tree=self.tree)
        #other = Leaf(self.tree, True)

        values = self.bucket.items()
        self.bucket = SortedDict(values[:len(values) // 2])
        other.bucket = SortedDict(values[len(values) // 2:])

        return (min(other.bucket), other)

    def _commit(self):
        pass
        #data = packb({
        #    'values': self.values,
        #})

        #self.tree.chunk.write(ChunkId.Leaf, data)
        #return self.tree.chunk.tell()

    def __getitem__(self, key):

        if key in self.bucket:
            return self.bucket[key]

        raise LookupError

    def __len__(self):
        return len(self.bucket)

    def __iter__(self):
        for key in self.bucket:
            yield key

class LazyNode(object):
    def __init__(self, tree, offset=None, node=None):
        super().__setattr__('tree', tree)
        super().__setattr__('offset', offset)
        super().__setattr__('node', node)

    def _load_node(self, data):
        data = unpackb(data)

        self.node = Node(tree=self.tree)
        self.node.rest = LazyNode(offset=data[b'rest'], tree=self.tree)
        self.node.values = SortedDict({k: LazyNode(offset=v, tree=self.tree) for
            k, v in data[b'values'].items()})

    def _load_leaf(self, data):
        data = unpackb(data)

        self.node = Leaf(tree=self.tree)
        self.node.values = SortedDict(data[b'values'])

    def _load(self):
        callbacks = {
            ChunkId.Node: self._load_node,
            ChunkId.Leaf: self._load_leaf,
        }

        self.tree.chunk.seek(self.offset)
        callback = callbacks.get(self.tree.chunk.get_id())

        if callback:
            callback(self.tree.chunk.read())

    def _commit(self):
        if not self.changed:
            return

        self.offset = self.node._commit()

    def __getattr__(self, name):
        if self.node is None:
            self._load()

        return getattr(self.node, name)

    def __setattr__(self, name, value):
        if name in self.__dict__:
            return super().__setattr__(name, value)

        setattr(self.node, name, value)

    def __getitem__(self, key):
        if self.node is None:
            self._load()

        return self.node[key]

    def __iter__(self):
        if self.node is None:
            self._load()

        yield from self.node.__iter__()

    def __len__(self):
        if self.node is None:
            self._load()

        return len(self.node)

def visualTree(tree):
    """
    Prints a visual representation of the tree
    :param tree:
    :return:
    """

    queue = q.Queue()

    depth = 0
    prevdepth = -1

    atdepth = [1,0]
    cur = 0;

    # At the root to the queue
    queue.put(tree.root)

    print("-- Root --")

    while not queue.empty():
        node = queue.get()
        atdepth[cur] -= 1

        # check if node is not a str instance
        if (isinstance(node, str)):
            return

        if depth != prevdepth:
            print("--- d=" + str(depth) + " ---")
            prevdepth = depth

        # For none leaf nodes, and if it has a rest attr print it with the left hand side pointer
        if type(node) is not Leaf and hasattr(node, 'rest') and node.rest != None:
            print(str(node.bucket) + " - lhs: " +  str(node.rest))
            queue.put(node.rest)
            atdepth[(cur + 1) % 2] += 1
        else:
            print(str(node.bucket))

        # Add the other neighboring nodes to the queue
        if node.bucket != None:
            for i in range(0, len(node.bucket)):
                #print(tree.__getitem__(bucket.iloc[i]))
                if type(node.bucket[node.bucket.iloc[i]]) != int:
                    queue.put(node.bucket[node.bucket.iloc[i]])
                    atdepth[(cur + 1) % 2] += 1

        if atdepth[cur] == 0:
            depth += 1
            cur = (cur + 1) % 2

def fillTree(tree):
    tree["1"] = "Value1"
    tree["2"] = "Value2"
    tree["3"] = "Value3"
    tree["4"] = "Value4"
    tree["5"] = "Value5"
    tree["6"] = "Value6"
    tree["7"] = "Value7"
    tree["8"] = "Value8"
    tree["9"] = "Value9"
    tree["10"] = "Value10"
    tree["11"] = "Value11"
    tree["12"] = "Value12"
    tree["13"] = "Value13"
    tree["14"] = "Value14"
    tree["15"] = "Value15"
    tree["16"] = "Value16"

    tree._commit()

def main():

    tree = Tree(max_size=4)
    fillTree(tree)

    try:
        print(tree.__getitem__("1"))
    except LookupError:
        print('Key not found!')

    visualTree(tree)

if __name__ == '__main__':
    main()
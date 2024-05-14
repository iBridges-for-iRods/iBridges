from typing import Union

import irods

from ibridges.path import IrodsPath


def get_dataobject(session,
                   path: Union[str, IrodsPath]) -> irods.data_object.iRODSDataObject:
    """Instantiate an iRODS data object.

    Parameters
    ----------
    session :
        Session with connection to the server to get the data object from.
    path : str
        Name of an iRODS data object.

    Raises
    ------
    ValueError:
        If the path is pointing to a collection and not a data object.

    Returns
    -------
    iRODSDataObject
        Instance of the data object with `path`.

    """
    path = IrodsPath(session, path)
    return path.dataobject

def get_collection(session,
                   path: Union[str, IrodsPath]) -> irods.collection.iRODSCollection:
    """Instantiate an iRODS collection.

    Parameters
    ----------
    session :
        Session to get the collection from.
    path : str
        Name of an iRODS collection.

    Raises
    ------
    ValueError:
        If the path points to a dataobject and not a collection.

    Returns
    -------
    iRODSCollection
        Instance of the collection with `path`.

    """
    return IrodsPath(session, path).collection


def get_size(session, item: Union[irods.data_object.iRODSDataObject,
                                  irods.collection.iRODSCollection]) -> int:
    """Collect the sizes of a data object or a collection.

    Parameters
    ----------
    session :
        Session with the connection to the item.
    item : iRODSDataObject or iRODSCollection
        Collection or data object to get the size of.

    Returns
    -------
    int :
        Total size [bytes] of the iRODS object or all iRODS objects in the collection.

    """
    return IrodsPath(session, item.path).size


def is_dataobject(item) -> bool:
    """Determine if item is an iRODS data object."""
    return isinstance(item, irods.data_object.iRODSDataObject)

def is_collection(item) -> bool:
    """Determine if item is an iRODS collection."""
    return isinstance(item, irods.collection.iRODSCollection)


def obj_replicas(obj: irods.data_object.iRODSDataObject) -> list[tuple[int, str, str, int, str]]:
    """Retrieve information about replicas (copies of the file on different resources).

    It does so for a data object in the iRODS system.

    Parameters
    ----------
    obj : irods.data_object.iRODSDataObject
        The data object

    Returns
    -------
    list(tuple(int, str, str, int, str)):
        List with tuple where each tuple contains replica index/number, resource name on which
        the replica is stored about one replica, replica checksum, replica size,
        replica status of the replica

    """
    #replicas = []
    repl_states = {
        '0': 'stale',
        '1': 'good',
        '2': 'intermediate',
        '3': 'write-locked'
    }

    replicas = [(r.number, r.resource_name, r.checksum,
                 r.size, repl_states.get(r.status, r.status)) for r in obj.replicas]

    return replicas

# coding: utf-8
# pylint: disable=C0103
"""
Defines:
  - mass_poperties
      get the mass & moment of inertia of the model
"""
from __future__ import print_function, unicode_literals
from collections import defaultdict
from six import string_types, iteritems
from numpy import array, cross, dot
from numpy.linalg import norm  # type: ignore
import numpy as np
from pyNastran.utils import integer_types
from pyNastran.utils.mathematics import integrate_positive_unit_line


def transform_inertia(mass, xyz_cg, xyz_ref, xyz_ref2, I_ref):
    """
    Transforms mass moment of inertia using parallel-axis theorem.

    Parameters
    ----------
    mass : float
        the mass
    xyz_cg : (3, ) float ndarray
        the CG location
    xyz_ref : (3, ) float ndarray
        the original reference location
    xyz_ref2 : (3, ) float ndarray
        the new reference location
    I_ref : (6, ) float ndarray
        the mass moment of inertias about the original reference point
        [Ixx, Iyy, Izz, Ixy, Ixz, Iyz]

    Returns
    -------
    I_new : (6, ) float ndarray
        the mass moment of inertias about the new reference point
        [Ixx, Iyy, Izz, Ixy, Ixz, Iyz]
    """
    xcg, ycg, zcg = xyz_cg
    xref, yref, zref = xyz_ref
    xref2, yref2, zref2 = xyz_ref2

    dx1 = xcg - xref
    dy1 = ycg - yref
    dz1 = zcg - zref

    dx2 = xref2 - xcg
    dy2 = yref2 - ycg
    dz2 = zref2 - zcg
    #print('dx1 = <%s, %s, %s>' % (dx1, dy1, dz1))
    #print('dx2 = <%s, %s, %s>' % (dx2, dy2, dz2))

    # consistent with mass_properties, not CONM2
    #print('I_ref =', I_ref)
    Ixx_ref, Iyy_ref, Izz_ref, Ixy_ref, Ixz_ref, Iyz_ref = I_ref
    Ixx2 = Ixx_ref - mass * (dx1**2 - dx2**2)
    Iyy2 = Iyy_ref - mass * (dy1**2 - dy2**2)
    Izz2 = Izz_ref - mass * (dz1**2 - dz2**2)
    Ixy2 = Ixy_ref - mass * (dx1 * dy1 - dx2 * dy2)
    Ixz2 = Ixz_ref - mass * (dx1 * dz1 - dx2 * dz2)
    Iyz2 = Iyz_ref - mass * (dy1 * dz1 - dy2 * dz2)
    I_new = np.array([Ixx2, Iyy2, Izz2, Ixy2, Ixz2, Iyz2])
    return I_new

def _mass_properties_elements_init(model, element_ids, mass_ids):
    """helper method"""
    # if neither element_id nor mass_ids are specified, use everything
    if isinstance(element_ids, integer_types):
        element_ids = [element_ids]
    if isinstance(mass_ids, integer_types):
        mass_ids = [mass_ids]

    if element_ids is None and mass_ids is None:
        elements = model.elements.values()
        masses = model.masses.values()

    # if either element_id or mass_ids are specified and the other is not, use only the
    # specified ids
    #
    # TODO: If eids are requested, but don't exist no warning is thrown.
    #       Decide if this is the desired behavior.
    else:
        if element_ids is None:
            elements = []
        else:
            assert len(model.elements) > 0
            elements = [element for eid, element in model.elements.items() if eid in element_ids]

        if mass_ids is None:
            masses = []
        else:
            assert len(model.masses) > 0
            masses = [mass for eid, mass in model.masses.items() if eid in mass_ids]
    return element_ids, elements, mass_ids, masses

def _mass_properties(model, elements, masses, reference_point):
    """
    Caclulates mass properties in the global system about the
    reference point.

    Parameters
    ----------
    model : BDF()
        a BDF object
    elements : List[int]; ndarray
        the element ids to consider
    masses : List[int]; ndarray
        the mass ids to consider
    reference_point : (3, ) ndarray; default = <0,0,0>.
        an array that defines the origin of the frame.

    Returns
    -------
    mass : float
        the mass of the model
    cg : (3, ) float NDARRAY
        the cg of the model as an array.
    I : (6, ) float NDARRAY
        moment of inertia array([Ixx, Iyy, Izz, Ixy, Ixz, Iyz])

    .. seealso:: model.mass_properties
    """
    #Ixx Iyy Izz, Ixy, Ixz Iyz
    # precompute the CG location and make it the reference point
    I = array([0., 0., 0., 0., 0., 0., ])
    cg = array([0., 0., 0.])
    if isinstance(reference_point, string_types):
        if reference_point == 'cg':
            mass = 0.
            for pack in [elements, masses]:
                for element in pack:
                    try:
                        p = element.Centroid()
                        m = element.Mass()
                        mass += m
                        cg += m * p
                    except:
                        pass
            if mass == 0.0:
                return mass, cg, I

            reference_point = cg / mass
        else:
            # reference_point = [0.,0.,0.] or user-defined array
            pass

    mass = 0.
    cg = array([0., 0., 0.])
    for pack in [elements, masses]:
        for element in pack:
            try:
                p = element.Centroid()
            except:
                continue

            try:
                m = element.Mass()
                #print('eid=%s type=%s mass=%s'  %(element.eid, element.type, m))
                (x, y, z) = p - reference_point
                x2 = x * x
                y2 = y * y
                z2 = z * z
                I[0] += m * (y2 + z2)  # Ixx
                I[1] += m * (x2 + z2)  # Iyy
                I[2] += m * (x2 + y2)  # Izz
                I[3] += m * x * y      # Ixy
                I[4] += m * x * z      # Ixz
                I[5] += m * y * z      # Iyz
                mass += m
                cg += m * p
            except:
                # PLPLANE
                if element.pid_ref.type == 'PSHELL':
                    model.log.warning('p=%s reference_point=%s type(reference_point)=%s' % (
                        p, reference_point, type(reference_point)))
                    raise
                model.log.warning("could not get the inertia for element/property\n%s%s" % (
                    element, element.pid_ref))
                continue

    #if model.nsms and 0:
        #bar_props = ['PBAR', 'PBARL', 'PBEAM', 'PBEAML', 'PBCOMP', 'PROD', 'PBEND', 'PTUBE', ]
        #shell_props = ['PSHELL', 'PCOMP',  'PSHEAR', 'PRAC2D',]
        ##nsm_properties = [
            ##'CONROD', 'ELEMENT', 'PCONEAX',
        ##]
        #bars = ['CBAR', 'CBEAM', 'CBEND', 'CROD', 'CTUBE', 'CONROD']
        #shells = ['CQUAD4', 'CQUAD8', 'CQUADR', 'CTRIA3', 'CTRIA6', 'CTRIAR', 'CSHEAR','CRAC2D']
        #length_pids_to_consider = []
        #length_eids_to_consider = []
        #area_pids_to_consider = []
        #area_eids_to_consider = []
        #nsm_id = 1
        #nsms = model.get_reduced_nsms(nsm_id, consider_nsmadd=True)
        #for prop in nsms:
            #if prop.type in ['NSM', 'NSM1']:
                #model.log.warning(prop.rstrip())

            #elif prop.type in ['NSML', 'NSML1']:
                #if prop.nsm_type in bar_props:
                    #length_pids_to_consider.append(prop.ids)
                    #length_mass_to_consider = [prop.value] * len(prop.ids)
                #elif prop.nsm_type in shell_props:
                    #area_pids_to_consider.append(prop.ids)
                    #area_mass_to_consider = [prop.value] * len(prop.ids)

                #elif prop.nsm_type == 'CONROD':
                    #length_eids_to_consider.append(prop.ids)
                    #length_mass_to_consider = [prop.value] * len(prop.ids)
                #elif prop.nsm_type == 'ELEMENT':
                    ## line element - CBAR, CBEAM, CBEND, CROD, CTUBE, and CONROD
                    ## area element - CQUAD4, CQUAD8, CQUADR, CTRIA3, CTRIA6, CTRIAR,
                    ##                CSHEAR, and CRAC2D
                    #pid0 = prop.ids[0]
                    #prop = model.properties[pid0]
                    #if prop.type in bars:
                        #length_pids_to_consider.append(prop.ids)
                    #elif prop.type in shells:
                        #area_pids_to_consider.append(prop.ids)
                    #else:
                        #model.log.warning(prop.rstrip())
                        #continue
                    #mass_to_consider =  [prop.value] * len(prop.ids)

                #prop.ids = ids
                #prop.value = value
                #asd
            #else:
                ## NSMADD - this shouldn't happen since we supposedly merged things
                #model.log.warning(prop.rstrip())

        #for prop in model.properties:
            #pass
    if mass:
        cg /= mass
    return (mass, cg, I)

def _mass_properties_no_xref(model, elements, masses, reference_point):  # pragma: no cover
    """
    Caclulates mass properties in the global system about the
    reference point.

    Parameters
    ----------
    model : BDF()
        a BDF object
    elements : List[int]; ndarray
        the element ids to consider
    masses : List[int]; ndarray
        the mass ids to consider
    reference_point : (3, ) ndarray; default = <0,0,0>.
        an array that defines the origin of the frame.

    Returns
    -------
    mass : float
        the mass of the model
    cg : (3, ) float NDARRAY
        the cg of the model as an array.
    I : (6, ) float NDARRAY
        moment of inertia array([Ixx, Iyy, Izz, Ixy, Ixz, Iyz])

    .. seealso:: self.mass_properties
    """
    #Ixx Iyy Izz, Ixy, Ixz Iyz
    # precompute the CG location and make it the reference point
    I = array([0., 0., 0., 0., 0., 0., ])
    cg = array([0., 0., 0.])
    if isinstance(reference_point, string_types):
        if reference_point == 'cg':
            mass = 0.
            for pack in [elements, masses]:
                for element in pack:
                    try:
                        p = element.Centroid_no_xref(model)
                        m = element.Mass_no_xref(model)
                        mass += m
                        cg += m * p
                    except:
                        #pass
                        raise
            if mass == 0.0:
                return mass, cg, I

            reference_point = cg / mass
        else:
            # reference_point = [0.,0.,0.] or user-defined array
            pass

    mass = 0.
    cg = array([0., 0., 0.])
    for pack in [elements, masses]:
        for element in pack:
            try:
                p = element.Centroid_no_xref(model)
            except:
                #continue
                raise

            try:
                m = element.Mass_no_xref(model)
                (x, y, z) = p - reference_point
                x2 = x * x
                y2 = y * y
                z2 = z * z
                I[0] += m * (y2 + z2)  # Ixx
                I[1] += m * (x2 + z2)  # Iyy
                I[2] += m * (x2 + y2)  # Izz
                I[3] += m * x * y      # Ixy
                I[4] += m * x * z      # Ixz
                I[5] += m * y * z      # Iyz
                mass += m
                cg += m * p
            except:
                # PLPLANE
                pid_ref = model.Property(element.pid)
                if pid_ref.type == 'PSHELL':
                    model.log.warning('p=%s reference_point=%s type(reference_point)=%s' % (
                        p, reference_point, type(reference_point)))
                    raise
                model.log.warning("could not get the inertia for element/property\n%s%s" % (
                    element, element.pid_ref))
                continue

    if mass:
        cg /= mass
    return (mass, cg, I)


def _increment_inertia(centroid, reference_point, m, mass, cg, I):
    """helper method"""
    (x, y, z) = centroid - reference_point
    x2 = x * x
    y2 = y * y
    z2 = z * z
    I[0] += m * (y2 + z2)  # Ixx
    I[1] += m * (x2 + z2)  # Iyy
    I[2] += m * (x2 + y2)  # Izz
    I[3] += m * x * y      # Ixy
    I[4] += m * x * z      # Ixz
    I[5] += m * y * z      # Iyz
    mass += m
    cg += m * centroid
    return mass

def _mass_properties_new(model, element_ids=None, mass_ids=None, nsm_id=None,
                         reference_point=None,
                         sym_axis=None, scale=None, xyz_cid0_dict=None,
                         debug=False):  # pragma: no cover
    """
    Caclulates mass properties in the global system about the
    reference point.

    Parameters
    ----------
    model : BDF()
        a BDF object
    element_ids : list[int]; (n, ) ndarray, optional
        An array of element ids.
    mass_ids : list[int]; (n, ) ndarray, optional
        An array of mass ids.
    nsm_id : int
        the NSM id to consider
    reference_point : ndarray/str/int, optional
        type : ndarray
            An array that defines the origin of the frame.
            default = <0,0,0>.
        type : str
            'cg' is the only allowed string
        type : int
            the node id
    sym_axis : str, optional
        The axis to which the model is symmetric.
        If AERO cards are used, this can be left blank.
        allowed_values = 'no', x', 'y', 'z', 'xy', 'yz', 'xz', 'xyz'
    scale : float, optional
        The WTMASS scaling value.
        default=None -> PARAM, WTMASS is used
        float > 0.0
    xyz_cid0_dict : dict[nid] : xyz; default=None -> auto-calculate
        mapping of the node id to the global position

    Returns
    -------
    mass : float
        The mass of the model.
    cg : ndarray
        The cg of the model as an array.
    I : ndarray
        Moment of inertia array([Ixx, Iyy, Izz, Ixy, Ixz, Iyz]).

    I = mass * centroid * centroid

    .. math:: I_{xx} = m (dy^2 + dz^2)

    .. math:: I_{yz} = -m * dy * dz

    where:

    .. math:: dx = x_{element} - x_{ref}

    .. seealso:: http://en.wikipedia.org/wiki/Moment_of_inertia#Moment_of_inertia_tensor

    .. note::
       This doesn't use the mass matrix formulation like Nastran.
       It assumes m*r^2 is the dominant term.
       If you're trying to get the mass of a single element, it
       will be wrong, but for real models will be correct.

    Examples
    --------
    **mass properties of entire structure**

    >>> mass, cg, I = model.mass_properties()
    >>> Ixx, Iyy, Izz, Ixy, Ixz, Iyz = I


    **mass properties of model based on Property ID**
    >>> pids = list(model.pids.keys())
    >>> pid_eids = model.get_element_ids_dict_with_pids(pids)
    >>> for pid, eids in sorted(iteritems(pid_eids)):
    >>>     mass, cg, I = mass_properties(model, element_ids=eids)

    TODO
    ----
     - fix NSML
     - fix CG for F:\work\pyNastran\examples\Dropbox\move_tpl\ac11102g.bdf
    """
    #if reference_point is None:
    reference_point = array([0., 0., 0.])

    if xyz_cid0_dict is None:
        xyz = {}
        for nid, node in iteritems(model.nodes):
            xyz[nid] = node.get_position()
    else:
        xyz = xyz_cid0_dict

    element_ids, unused_elements, mass_ids, unused_masses = _mass_properties_elements_init(
        model, element_ids, mass_ids)

    #mass = 0.
    #cg = array([0., 0., 0.])
    #I = array([0., 0., 0., 0., 0., 0., ])
    #if isinstance(reference_point, string_types):
        #if reference_point == 'cg':
            #mass = 0.
            #for pack in [elements, masses]:
                #for element in pack:
                    #try:
                        #p = element.Centroid()
                        #m = element.Mass()
                        #mass += m
                        #cg += m * p
                    #except:
                        #pass
            #if mass == 0.0:
                #return mass, cg, I

            #reference_point = cg / mass
        #else:
            ## reference_point = [0.,0.,0.] or user-defined array
            #pass

    mass = 0.
    cg = array([0., 0., 0.])
    I = array([0., 0., 0., 0., 0., 0., ])

    all_eids = np.array(list(model.elements.keys()), dtype='int32')
    all_eids.sort()

    all_mass_ids = np.array(list(model.masses.keys()), dtype='int32')
    all_mass_ids.sort()

    #element_nsms, property_nsms = _get_nsm_data(model, nsm_id, debug=debug)
    #def _increment_inertia0(centroid, reference_point, m, mass, cg, I):
        #"""helper method"""
        #(x, y, z) = centroid - reference_point
        #mass += m
        #cg += m * centroid
        #return mass

    etypes_skipped = set([])
    #eid_areas = defaultdict(list)
    area_eids_pids = defaultdict(list)
    areas = defaultdict(list)
    nsm_centroids_area = defaultdict(list)

    length_eids_pids = defaultdict(list)
    nsm_centroids_length = defaultdict(list)
    lengths = defaultdict(list)

    no_mass = [
        'CELAS1', 'CELAS2', 'CELAS3', 'CELAS4', #'CLEAS5',
        'CDAMP1', 'CDAMP2', 'CDAMP3', 'CDAMP4', 'CDAMP5',
        'CBUSH', 'CBUSH1D', 'CBUSH2D', 'CVISC', 'CGAP', # is this right?
        'CFAST',
        'CRAC2D', 'CRAC3D',

        'CSSCHD', 'CAERO1', 'CAERO2', 'CAERO3', 'CAERO4', 'CAERO5',
        'CBARAO', 'CORD1R', 'CORD2R', 'CORD1C', 'CORD2C', 'CORD1S', 'CORD2S',
        'CORD3G', 'CONV', 'CONVM', 'CLOAD',
        'CHBDYG', 'CHBDYE', 'CHBDYP',

        'CTRAX3', 'CTRAX6', 'CQUADX8', 'CQUADX4',
        'CPLSTN3', 'CPLSTN6', 'CPLSTN4', 'CPLSTN8',

        'ASET', 'ASET1', 'BSET', 'BSET1', 'CSET', 'CSET1',
        'QSET', 'QSET1', 'USET', 'USET1',
    ]
    for etype, eids in iteritems(model._type_to_id_map):
        if etype in no_mass:
            continue
        mass, cg, I = _get_mass_new(
            model, all_eids, all_mass_ids, etypes_skipped,
            etype, eids, xyz,
            length_eids_pids, nsm_centroids_length, lengths,
            area_eids_pids, nsm_centroids_area, areas,
            mass, cg, I, reference_point)

    model_eids = np.array(list(model.elements.keys()), dtype='int32')
    model_pids = np.array(list(model.properties.keys()), dtype='int32')
    if debug:  # pragma: no cover
        model.log.debug('model_pids = %s' % model_pids)
    mass = _apply_nsm(model, nsm_id,
                      model_eids, model_pids,
                      area_eids_pids, areas, nsm_centroids_area,
                      length_eids_pids, lengths, nsm_centroids_length,
                      mass, cg, I, reference_point, debug=debug)
    assert mass is not None
    if mass:
        cg /= mass
    mass, cg, I = _apply_mass_symmetry(model, sym_axis, scale, mass, cg, I)
    # Ixx, Iyy, Izz, Ixy, Ixz, Iyz = I
    return mass, cg, I


def get_sub_eids(all_eids, eids):
    """supports limiting the element/mass ids"""
    eids = np.array(eids)
    ieids = np.searchsorted(all_eids, eids)
    eids2 = eids[all_eids[ieids] == eids]
    return eids2

def _get_mass_new(model, all_eids, all_mass_ids, etypes_skipped,
                  etype, eids, xyz,
                  length_eids_pids, nsm_centroids_length, lengths,
                  area_eids_pids, nsm_centroids_area, areas,
                  mass, cg, I, reference_point):
    if len(eids) == 0:
        pass
    elif etype in ['CROD', 'CONROD']:
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2 = elem.node_ids
            length = norm(xyz[n2] - xyz[n1])
            centroid = (xyz[n1] + xyz[n2]) / 2.
            mpl = elem.MassPerLength()
            if elem.type == 'CONROD':
                #nsm = property_nsms[nsm_id]['CONROD'][eid] + element_nsms[nsm_id][eid]
                length_eids_pids['CONROD'].append((eid, -42))  # faked number
                lengths['CONROD'].append(length)
                nsm_centroids_length['CONROD'].append(centroid)
            else:
                pid = elem.pid
                #nsm = property_nsms[nsm_id]['PROD'][pid] + element_nsms[nsm_id][eid]
                length_eids_pids['PROD'].append((eid, pid))
                nsm_centroids_length['PROD'].append(centroid)
                lengths['PROD'].append(length)
            #m = (mpl + nsm) * length
            massi = mpl * length
            if massi != elem.Mass():
                msg = 'mass_new=%s mass_old=%s\n%s' % (massi, elem.Mass(), str(elem))
                raise RuntimeError(msg)
            mass = _increment_inertia(centroid, reference_point, massi, mass, cg, I)
    elif etype == 'CTUBE':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            pid = elem.pid
            n1, n2 = elem.node_ids
            length = norm(xyz[n2] - xyz[n1])
            centroid = (xyz[n1] + xyz[n2]) / 2.
            mpl = elem.pid_ref.MassPerLength()
            length_eids_pids['PTUBE'].append((eid, pid))
            lengths['PTUBE'].append(length)
            #nsm = property_nsms[nsm_id]['PTUBE'][pid] + element_nsms[nsm_id][eid]
            #m = (mpl + nsm) * length
            massi = mpl * length
            if massi != elem.Mass():
                msg = 'mass_new=%s mass_old=%s\n%s' % (massi, elem.Mass(), str(elem))
                raise RuntimeError(msg)
            mass = _increment_inertia(centroid, reference_point, massi, mass, cg, I)
    elif etype == 'CBAR':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            pid = elem.pid
            n1, n2 = elem.node_ids
            centroid = (xyz[n1] + xyz[n2]) / 2.
            length = norm(xyz[n2] - xyz[n1])
            mpl = elem.pid_ref.MassPerLength()
            length_eids_pids['PBAR'].append((eid, pid))
            lengths['PBAR'].append(length)
            nsm_centroids_length['PBAR'].append(centroid)
            #nsm = property_nsms[nsm_id]['PBAR'][pid] + element_nsms[nsm_id][eid]
            #m = (mpl + nsm) * length
            massi = mpl * length
            if massi != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (massi, elem.Mass())
                msg += 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            mass = _increment_inertia(centroid, reference_point, massi, mass, cg, I)
    elif etype == 'CBEAM':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            prop = elem.pid_ref
            pid = elem.pid
            n1, n2 = elem.node_ids
            node1 = xyz[n1]
            node2 = xyz[n2]
            centroid = (node1 + node2) / 2.
            length = norm(node2 - node1)
            #cda = model.nodes[n1].cid_ref
            #cdb = model.nodes[n2].cid_ref

            ## TODO: fix bar axes
            is_failed, out = elem.get_axes(model)
            if is_failed:
                model.log.error(out)
                raise RuntimeError(out)
            wa, wb, _ihat, jhat, khat = out
            p1 = node1 + wa
            p2 = node2 + wb
            if prop.type == 'PBEAM':
                rho = prop.Rho()
                mass_per_lengths = []
                nsm_per_lengths = []
                for (area, nsm) in zip(prop.A, prop.nsm):
                    mass_per_lengths.append(area * rho)
                    nsm_per_lengths.append(nsm)
                mass_per_length = integrate_positive_unit_line(prop.xxb, mass_per_lengths)
                nsm_per_length = integrate_positive_unit_line(prop.xxb, nsm_per_lengths)
                nsm_n1 = (p1 + jhat * prop.m1a + khat * prop.m2a)
                nsm_n2 = (p2 + jhat * prop.m1b + khat * prop.m2b)
                nsm_centroid = (nsm_n1 + nsm_n2) / 2.
                #if nsm != 0.:
                    #p1_nsm = p1 + prop.ma
                    #p2_nsm = p2 + prop.mb
            elif prop.type == 'PBEAML':
                mass_per_lengths = prop.get_mass_per_lengths()
                #mass_per_length = prop.MassPerLength() # includes simplified nsm

                # m1a, m1b, m2a, m2b=0.
                nsm_centroid = (p1 + p2) / 2.
                nsm_per_lengths = prop.nsm
                mass_per_length = integrate_positive_unit_line(prop.xxb, mass_per_lengths)
                nsm_per_length = integrate_positive_unit_line(prop.xxb, nsm_per_lengths)
                #print('mass_per_lengths=%s nsm_per_lengths=%s' % (
                    #mass_per_lengths, nsm_per_lengths))
                #print('mass_per_length=%s nsm_per_length=%s' % (
                    #mass_per_length, nsm_per_length))

                #nsm_centroid = np.zeros(3) # TODO: what is this...
                #nsm = prop.nsm[0] * length # TODO: simplified
            elif prop.type == 'PBCOMP':
                mass_per_length = prop.MassPerLength()
                nsm_per_length = prop.nsm
                nsm_n1 = (p1 + jhat * prop.m1 + khat * prop.m2)
                nsm_n2 = (p2 + jhat * prop.m1 + khat * prop.m2)
                nsm_centroid = (nsm_n1 + nsm_n2) / 2.
            elif prop.type == 'PBMSECT':
                continue
                #mass_per_length = prop.MassPerLength()
                #m = mass_per_length * length
                #nsm = prop.nsm
            else:
                raise NotImplementedError(prop.type)

            #mpl = elem.pid_ref.MassPerLength()
            #m = mpl * length

            length_eids_pids['PBEAM'].append((eid, pid))
            lengths['PBEAM'].append(length)
            nsm_centroids_length['PBEAM'].append(nsm_centroid)
            m = mass_per_length * length
            if m != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (m, elem.Mass())
                msg += 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            #nsmi = property_nsms[nsm_id]['PBEAM'][pid] + element_nsms[nsm_id][eid] * length
            #nsm = (nsm_per_length + nsmi) * length
            nsm = nsm_per_length * length
            (x, y, z) = centroid - reference_point
            (xm, ym, zm) = nsm_centroid - reference_point
            x2 = x * x
            y2 = y * y
            z2 = z * z
            xm2 = xm * xm
            ym2 = ym * ym
            zm2 = zm * zm

            # Ixx, Iyy, Izz, Ixy, Ixz, Iyz
            I[0] += m * (y2 + z2) + nsm * (ym2 + zm2)
            I[1] += m * (x2 + z2) + nsm * (xm2 + zm2)
            I[2] += m * (x2 + y2) + nsm * (xm2 + ym2)
            I[3] += m * x * y + nsm * xm * ym
            I[4] += m * x * z + nsm * xm * zm
            I[5] += m * y * z + nsm * ym * zm
            mass += m + nsm
            cg += m * centroid + nsm * nsm_centroid

    elif etype in ['CTRIA3', 'CTRIA6', 'CTRIAR']:
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3 = elem.node_ids[:3]
            prop = elem.pid_ref
            pid = elem.pid
            centroid = (xyz[n1] + xyz[n2] + xyz[n3]) / 3.
            area = 0.5 * norm(cross(xyz[n1] - xyz[n2], xyz[n1] - xyz[n3]))
            #areas_prop[pid] += area
            if prop.type == 'PSHELL':
                tflag = elem.tflag
                ti = prop.Thickness()
                if tflag == 0:
                    # absolute
                    t1 = elem.T1 if elem.T1 else ti
                    t2 = elem.T2 if elem.T2 else ti
                    t3 = elem.T3 if elem.T3 else ti
                elif tflag == 1:
                    # relative
                    t1 = elem.T1 * ti if elem.T1 else ti
                    t2 = elem.T2 * ti if elem.T2 else ti
                    t3 = elem.T3 * ti if elem.T3 else ti
                else:
                    raise RuntimeError('tflag=%r' % tflag)
                assert t1 + t2 + t3 > 0., 't1=%s t2=%s t3=%s' % (t1, t2, t3)
                t = (t1 + t2 + t3) / 3.

                # m/A = rho * A * t + nsm
                #mass_per_area = elem.nsm + rho * elem.t

                #areas_prop[pid] += area
                mpa = prop.nsm + prop.Rho() * t
                #mpa = elem.pid_ref.MassPerArea()
                m = mpa * area
            elif prop.type in ['PCOMP', 'PCOMPG']:
                # PCOMP, PCOMPG
                #rho_t = prop.get_rho_t()
                #nsm = prop.nsm
                #rho_t = [mat.Rho() * t for (mat, t) in zip(prop.mids_ref, prop.ts)]
                #mpa = sum(rho_t) + nsm

                # works for PCOMP
                # F:\Program Files\Siemens\NXNastran\nxn10p1\nxn10p1\nast\tpl\cqr3compbuck.dat
                mpa = prop.get_mass_per_area()
            elif prop.type == 'PLPLANE':
                continue
            else:
                raise NotImplementedError(prop.type)
            area_eids_pids['PSHELL'].append((eid, pid))
            areas['PSHELL'].append(area)

            nsm_centroids_area['PSHELL'].append(centroid)
            #nsm = property_nsms[nsm_id]['PSHELL'][pid] + element_nsms[nsm_id][eid]
            #m = area * (mpa + nsm)
            massi = area * mpa
            if not np.array_equal(centroid, elem.Centroid()):
                msg = 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            mass = _increment_inertia(centroid, reference_point, massi, mass, cg, I)
    elif etype in ['CQUAD4', 'CQUAD8', 'CQUADR']:
        eids2 = get_sub_eids(all_eids, eids)
        #eid0 = eids2[0]
        #elem0 = model.elements[eid0]
        #pid = elem0.pid
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3, n4 = elem.node_ids[:4]
            prop = elem.pid_ref
            pid = prop.pid
            centroid = (xyz[n1] + xyz[n2] + xyz[n3] + xyz[n4]) / 4.
            area = 0.5 * norm(cross(xyz[n3] - xyz[n1], xyz[n4] - xyz[n2]))

            if prop.type == 'PSHELL':
                tflag = elem.tflag
                ti = prop.Thickness()
                if tflag == 0:
                    # absolute
                    t1 = elem.T1 if elem.T1 else ti
                    t2 = elem.T2 if elem.T2 else ti
                    t3 = elem.T3 if elem.T3 else ti
                    t4 = elem.T4 if elem.T4 else ti
                elif tflag == 1:
                    # relative
                    t1 = elem.T1 * ti if elem.T1 else ti
                    t2 = elem.T2 * ti if elem.T2 else ti
                    t3 = elem.T3 * ti if elem.T3 else ti
                    t4 = elem.T4 * ti if elem.T4 else ti
                else:
                    raise RuntimeError('tflag=%r' % tflag)
                assert t1 + t2 + t3 + t4 > 0., 't1=%s t2=%s t3=%s t4=%s' % (t1, t2, t3, t4)
                t = (t1 + t2 + t3 + t4) / 4.

                # m/A = rho * A * t + nsm
                #mass_per_area = model.nsm + rho * model.t

                #areas_prop[pid] += area
                mpa = prop.nsm + prop.Rho() * t
                #mpa = elem.pid_ref.MassPerArea()
                #m = mpa * area
            elif prop.type in ['PCOMP', 'PCOMPG']:
                # PCOMP, PCOMPG
                #rho_t = prop.get_rho_t()
                #nsm = prop.nsm
                #rho_t = [mat.Rho() * t for (mat, t) in zip(prop.mids_ref, prop.ts)]
                #mpa = sum(rho_t) + nsm
                mpa = prop.get_mass_per_area()
            elif prop.type == 'PLPLANE':
                continue
                #raise NotImplementedError(prop.type)
            else:
                raise NotImplementedError(prop.type)
            area_eids_pids['PSHELL'].append((eid, pid))
            areas['PSHELL'].append(area)
            nsm_centroids_area['PSHELL'].append(centroid)
            #nsm = property_nsms[nsm_id]['PSHELL'][pid] + element_nsms[nsm_id][eid]
            #m = area * (mpa + nsm)
            m = area * mpa
            if not np.array_equal(centroid, elem.Centroid()):
                msg = 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            #print('eid=%s type=%s mass=%s; area=%s mpa=%s'  %(elem.eid, elem.type, m, area, mpa))
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
    elif etype == 'CQUAD':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3, n4 = elem.node_ids[:4]
            prop = elem.pid_ref
            centroid = (xyz[n1] + xyz[n2] + xyz[n3] + xyz[n4]) / 4.
            area = 0.5 * norm(cross(xyz[n3] - xyz[n1], xyz[n4] - xyz[n2]))

            if prop.type == 'PSHELL':
                t = prop.Thickness()
                mpa = prop.nsm + prop.Rho() * t
            elif prop.type in ['PCOMP', 'PCOMPG']:
                mpa = prop.get_mass_per_area()
            elif prop.type == 'PLPLANE':
                continue
                #raise NotImplementedError(prop.type)
            else:
                raise NotImplementedError(prop.type)
            m = area * mpa
            if m != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (m, elem.Mass())
                msg += 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)

    elif etype == 'CSHEAR':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3, n4 = elem.node_ids
            prop = elem.pid_ref
            pid = elem.pid
            centroid = (xyz[n1] + xyz[n2] + xyz[n3] + xyz[n4]) / 4.
            area = 0.5 * norm(cross(xyz[n3] - xyz[n1], xyz[n4] - xyz[n2]))
            mpa = prop.MassPerArea()

            area_eids_pids['PSHEAR'].append((eid, pid))
            areas['PSHEAR'].append(area)
            nsm_centroids_area['PSHEAR'].append(centroid)

            #nsm = property_nsms[nsm_id]['PSHEAR'][pid] + element_nsms[nsm_id][eid]
            #m = area * (mpa + nsm)
            m = area * mpa
            if m != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (m, elem.Mass)
                msg += 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
    elif etype in ['CONM1', 'CONM2', 'CMASS1', 'CMASS2', 'CMASS3', 'CMASS4']:
        eids2 = get_sub_eids(all_mass_ids, eids)
        for eid in eids2:
            elem = model.masses[eid]
            m = elem.Mass()
            centroid = elem.Centroid()
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
    elif etype == 'CTETRA':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3, n4 = elem.node_ids[:4]
            centroid = (xyz[n1] + xyz[n2] + xyz[n3] + xyz[n4]) / 4.
            #V = -dot(n1 - n4, cross(n2 - n4, n3 - n4)) / 6.
            volume = -dot(xyz[n1] - xyz[n4], cross(xyz[n2] - xyz[n4], xyz[n3] - xyz[n4])) / 6.
            m = elem.Rho() * volume
            if m != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (m, elem.Mass())
                msg += 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
    elif etype == 'CPYRAM':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3, n4, n5 = elem.node_ids[:5]
            centroid1 = (xyz[n1] + xyz[n2] + xyz[n3] + xyz[n4]) / 4.
            area1 = 0.5 * norm(cross(xyz[n3]-xyz[n1], xyz[n4]-xyz[n2]))
            centroid5 = xyz[n5]

            #V = (l * w) * h / 3
            #V = A * h / 3
            centroid = (centroid1 + centroid5) / 2.

            #(n1, n2, n3, n4, n5) = self.get_node_positions()
            #area1, c1 = area_centroid(n1, n2, n3, n4)
            #volume = area1 / 3. * norm(c1 - n5)
            volume = area1 / 3. * norm(centroid1 - centroid5)
            m = elem.Rho() * volume
            if m != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (m, elem.Mass())
                msg += 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            #print('*eid=%s type=%s mass=%s rho=%s V=%s' % (
                #elem.eid, 'CPYRAM', m, elem.Rho(), volume))
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
    elif etype == 'CPENTA':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3, n4, n5, n6 = elem.node_ids[:6]
            area1 = 0.5 * norm(cross(xyz[n3] - xyz[n1], xyz[n2] - xyz[n1]))
            area2 = 0.5 * norm(cross(xyz[n6] - xyz[n4], xyz[n5] - xyz[n4]))
            centroid1 = (xyz[n1] + xyz[n2] + xyz[n3]) / 3.
            centroid2 = (xyz[n4] + xyz[n5] + xyz[n6]) / 3.
            centroid = (centroid1 + centroid2) / 2.
            volume = (area1 + area2) / 2. * norm(centroid1 - centroid2)
            m = elem.Rho() * volume
            if m != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (m, elem.Mass())
                msg += 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            #print('*eid=%s type=%s mass=%s rho=%s V=%s' % (
                #elem.eid, 'CPENTA', m, elem.Rho(), volume))
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)

    elif etype == 'CHEXA':
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]
            n1, n2, n3, n4, n5, n6, n7, n8 = elem.node_ids[:8]
            #(A1, c1) = area_centroid(n1, n2, n3, n4)
            centroid1 = (xyz[n1] + xyz[n2] + xyz[n3] + xyz[n4]) / 4.
            area1 = 0.5 * norm(cross(xyz[n3] - xyz[n1], xyz[n4] - xyz[n2]))
            #(A2, c2) = area_centroid(n5, n6, n7, n8)
            centroid2 = (xyz[n5] + xyz[n6] + xyz[n7] + xyz[n8]) / 4.
            area2 = 0.5 * norm(cross(xyz[n7] - xyz[n5], xyz[n8] - xyz[n6]))

            volume = (area1 + area2) / 2. * norm(centroid1 - centroid2)
            m = elem.Rho() * volume
            centroid = (centroid1 + centroid2) / 2.
            if m != elem.Mass() or not np.array_equal(centroid, elem.Centroid()):
                msg = 'mass_new=%s mass_old=%s\n' % (m, elem.Mass())
                msg = 'centroid_new=%s centroid_old=%s\n%s' % (
                    str(centroid), str(elem.Centroid()), str(elem))
                raise RuntimeError(msg)
            #print('*centroid1=%s centroid2=%s' % (str(centroid1), str(centroid2)))
            #print('*area1=%s area2=%s length=%s' % (area1, area2, norm(centroid1 - centroid2)))
            #print('*eid=%s type=%s mass=%s rho=%s V=%s' % (
                #elem.eid, 'CHEXA', m, elem.Rho(), volume))
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)

    elif etype == 'CBEND':
        model.log.info('elem.type=%s doesnt have mass' % etype)
        #nsm = property_nsms[nsm_id]['PBEND'][pid] + element_nsms[nsm_id][eid]
    elif etype.startswith('C'):
        eids2 = get_sub_eids(all_eids, eids)
        for eid in eids2:
            elem = model.elements[eid]

            #if elem.pid_ref.type in ['PPLANE']:
            try:
                m = elem.Mass()
            except:
                model.log.error('etype = %r' % etype)
                model.log.error(elem)
                model.log.error(elem.pid_ref)
                raise
            centroid = elem.Centroid()
            if m > 0.0:
                model.log.info('elem.type=%s is not supported in new '
                               'mass properties method' % elem.type)
                mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
            elif etype not in etypes_skipped:
                model.log.info('elem.type=%s doesnt have mass' % elem.type)
                etypes_skipped.add(etype)


    #property_nsms[nsm_id][nsm.nsm_type][nsm_idi]
    #for nsm_id, prop_types in sorted(iteritems(property_nsms)):
        #for prop_type, prop_id_to_val in sorted(iteritems(prop_types)):
            #for pid, val in sorted(iteritems(prop_id_to_val)):
        #TODO: CRAC2D mass not supported...how does this work???
        #      I know it's an "area" element similar to a CQUAD4
        #TODO: CCONEAX mass not supported...how does this work???
        #TODO: CBEAM/PBCOMP mass not supported...how does this work???
        #TODO: CBEND mass not supported...how do I calculate the length?

        #area_eids['PSHELL'].append(eid)
        #areas['PSHELL'].append(area)
    return mass, cg, I

def _setup_apply_nsm(area_eids_pids, areas, nsm_centroids_area,
                     length_eids_pids, lengths, nsm_centroids_length):
    """
    Sets up the non-structural mass processing

    Parameters
    ----------
    area_eids_pids
    areas : ???
        ????
    nsm_centroids_area : ???
        ????
    length_eids_pids : ???
        ????
    lengths : ???
        ????
    nsm_centroids_length : ???
        ????

    Returns
    -------
    all_eids_pids : ???
        ???
    area_length : ???
        ???
    is_area : (nelements, ) bool ndarray
        is this an area element
    nsm_centroids : (nelements, 3 ) float ndarray
        the centroids for the elements
    """
    nsm_centroids = []
    all_eids_pids = []
    area_length = []
    is_area = []
    #is_data = False
    #print(areas)
    for ptype, eids_pids in iteritems(area_eids_pids):
        areasi = np.array(areas[ptype], dtype='float64')
        area_eids_pids[ptype] = np.array(eids_pids, dtype='int32')
        areas[ptype] = areasi
        assert len(areasi) > 0, areas
        all_eids_pids += eids_pids
        nsm_centroidsi = np.array(nsm_centroids_area[ptype])
        nsm_centroids.append(nsm_centroidsi)
        assert len(eids_pids) == len(nsm_centroids_area[ptype]), ptype
        #print(areasi)
        area_length.append(areasi)
        is_area += [True] * len(areasi)
        #is_data = True
        nsm_centroids_area[ptype] = nsm_centroidsi

    for ptype, eids_pids in iteritems(length_eids_pids):
        lengthsi = np.array(lengths[ptype], dtype='float64')
        length_eids_pids[ptype] = np.array(eids_pids, dtype='int32')
        lengths[ptype] = lengthsi
        assert len(lengthsi) > 0, lengthsi
        all_eids_pids += eids_pids
        nsm_centroidsi = np.array(nsm_centroids_length[ptype])
        nsm_centroids.append(nsm_centroidsi)
        assert len(eids_pids) == len(nsm_centroids_length[ptype]), ptype
        #print(lengthsi)
        area_length.append(lengthsi)
        is_area += [False] * len(lengthsi)
        #is_data = True
        nsm_centroids_length[ptype] = nsm_centroidsi

    all_eids_pids = np.array(all_eids_pids, dtype='int32')
    if len(area_eids_pids) == 0:
        return all_eids_pids, area_length, is_area, nsm_centroids

    #print(all_eids_pids)
    isort = np.argsort(all_eids_pids[:, 0])
    #print('isort =', isort)
    all_eids_pids = all_eids_pids[isort, :]
    area_length = np.hstack(area_length)[isort]

    is_area = np.array(is_area, dtype='bool')[isort]
    nsm_centroids = np.vstack(nsm_centroids)[isort]
    return all_eids_pids, area_length, is_area, nsm_centroids

def _combine_prop_weighted_area_length_simple(
        model, eids, area, centroids,
        nsm_value, reference_point, mass, cg, I,
        is_area, divide_by_sum,
        debug=True):
    """
    Calculates the contribution of NSM/NSML/NSM1 cards on mass properties.
    Area/Length are abstracted, so if you have a shell element, the area_sum
    is an area_sum, whereas if you have a line element, it's a lenght_sum.

    The standard (non-NSM card) shell mass is calculated as:
        mass = A * (nsm_per_unit_area + t * rho)

    For an NSM/NSM1 card, we simply modify nsm_per_unit_area either on a
    per element basis or property basis.

    The following NSM/NSML cards area identical (for any number of elements) ::

        NSML, 42, ELEMENT, 100, 0.1
        NSM,  42, ELEMENT, 100, 0.1

    However, the following NSM/NSML property cards are different:
        NSML, 42, PSHELL, 100, 0.1
        NSM,  42, PSHELL, 100, 0.1

    The NSM card defines nsm_unit_area,  while NSML defines
    total nsm  or ``A*nsm_per_unit_area``.
    """
    if debug:  # pragma: no cover
        model.log.debug('_combine_weighted_area_length_simple')
    assert nsm_value is not None
    if len(area) != len(centroids):
        msg = 'len(area)=%s len(centroids)=%s ' % (len(area), len(centroids))
        raise RuntimeError(msg)

    if is_area:
        word = 'area'
    else:
        word = 'length'
    area_sum = 0.0
    if divide_by_sum:
        for eid, areai, centroid in zip(eids, area, centroids):
            area_sum += areai
        area = area / area_sum
        if debug:
            model.log.debug('dividing by %s=%s' % (word, area_sum))

    for eid, areai, centroid in zip(eids, area, centroids):
        #area_sum += areai
        m = nsm_value * areai
        if debug:  # pragma: no cover
            model.log.debug('  eid=%s %si=%s nsm_value=%s mass=%s' % (
                eid, word, areai, nsm_value, m))
        mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
    if debug:  # pragma: no cover
        model.log.debug('%s sum = %s' % (word, area_sum))
    return mass

def _combine_prop_weighted_area_length(
        model, areas_ipids, nsm_centroidsi, is_area, area_sum,
        nsm_value, reference_point, mass, cg, I, debug=True):
    """
    Calculates the contribution of NSML cards on mass properties.
    Area/Length are abstracted, so if you have a shell element, the area_sum
    is an area_sum, whereas if you have a line element, it's a lenght_sum.

    The NSML mass contribution is calculated as a distrubted mass:
        mass = nsm_per_unit_area * areai / area_sum
    """
    assert area_sum is not None
    assert nsm_value is not None
    if is_area:
        word = 'area'
    else:
        word = 'length'

    for (area, ipid) in areas_ipids:
        if debug:  # pragma: no cover
            model.log.debug("  nsm_centroidsi = %s" % nsm_centroidsi)
        centroids = nsm_centroidsi[ipid, :]

        area2 = area / area_sum
        for areai, centroid in zip(area2, centroids):
            #print('  areai=%s area_sum=%s nsm_value=%s' % (areai*area_sum, area_sum, nsm_value))
            m = nsm_value * areai
            if debug:  # pragma: no cover
                model.log.debug('  %si=%s %s_sum=%s nsm_value=%s mass=%s' % (
                    word, areai*area_sum, word, area_sum, nsm_value, m))
            mass = _increment_inertia(centroid, reference_point, m, mass, cg, I)
    return mass

def _apply_nsm(model, nsm_id,
               unused_model_eids, unused_model_pids,
               area_eids_pids, areas, nsm_centroids_area,
               length_eids_pids, lengths, nsm_centroids_length,
               mass, cg, I, reference_point, debug=False):
    """
    Applies NSM cards to the mass, cg, and inertia.

    Parameters
    ----------
    model : BDF()
        a BDF object
    nsm_id : int
        the NSM id to consider
    reference_point : ndarray/str/int, optional
        type : ndarray
            An array that defines the origin of the frame.
            default = <0,0,0>.
        type : str
            'cg' is the only allowed string
        type : int
            the node id
    area_eids_pids : Dict[etype_ptype] = eids_pids
        etype_ptype : str
            the element or property type (e.g., CQUAD4, PSHELL)
        eids_pids : (neids, 2) ndarray
            (element_id, property_id) for area elements
    areas : Dict[etype_ptype] = area
        area : (nelements, ) float ndarray
            area for area elements
    nsm_centroids_area : Dict[etype_ptype] = centroids
        centroids : (nelements, 3) float ndarray
            centroids for area elements
    length_eids_pids : Dict[etype_ptype] = eids_pids
        etype_ptype : str
            the element or property type (e.g., CQUAD4, PSHELL)
        eids_pids : (neids, 2) ndarray
            (element_id, property_id) for area elements
    lengths :  Dict[etype_ptype] = length
        length : (nelements, ) float ndarray
            lengths for length elements (e.g., CBAR, PBEAM, CONROD)
    nsm_centroids_length : Dict[etype_ptype] = centroids
        centroids : (nelements, 3) float ndarray
            centroids for length elements
    mass : float
        The mass of the model
    cg : ndarray
        The cg of the model as an array
    I : ndarray
        Moment of inertia array([Ixx, Iyy, Izz, Ixy, Ixz, Iyz])

    Returns
    -------
    mass : float
        The mass of the model

    per MSC QRG 2018.0.1: Undefined property/element IDs are ignored.
    TODO: support ALL
    """
    if not nsm_id:
        return mass

    #print(length_eids_pids)
    #print(lengths)
    nsms = model.get_reduced_nsms(nsm_id, consider_nsmadd=True, stop_on_failure=True)
    if debug:  # pragma: no cover
        for nsm in nsms:
            model.log.debug(nsm.rstrip())

    nsm_type_map = {
        'PSHELL' : 'PSHELL',
        'PCOMP' : 'PSHELL',
        'PCOMPG' : 'PSHELL',

        'PBAR' : 'PBAR',
        'PBARL' : 'PBAR',

        'PBEAM' : 'PBEAM',
        'PBEAML' : 'PBEAM',
        'PBCOMP' : 'PBEAM',

        'PROD' : 'PROD',
        'PBEND' : 'PBEND',
        'PSHEAR' : 'PSHEAR',
        'PTUBE' : 'PTUBE',
        'PCONEAX' : 'PCONEAX',
        'PRAC2D' : 'PRAC2D',
        'CONROD' : 'CONROD',
        'ELEMENT' : 'ELEMENT',
    }

    #all_eid_nsms = []
    if len(nsms) == 0:
        model.log.warning('no nsm...')
        return mass

    all_eids_pids, area_length, is_area_array, nsm_centroids = _setup_apply_nsm(
        area_eids_pids, areas, nsm_centroids_area,
        length_eids_pids, lengths, nsm_centroids_length)

    if len(all_eids_pids) == 0:
        model.log.debug('  skipping NSM=%s calc because there are no elements\n' % nsm_id)
        return mass

    #print('all_eids_pids =', all_eids_pids)
    #print('area_length =', area_length)
    #print('is_area =', is_area)
    #area_length = area_length[isort]
    #is_area = is_area[isort]

    for nsm in nsms:
        nsm_value = nsm.value
        nsm_type = nsm_type_map[nsm.nsm_type]
        if debug:  # pragma: no cover
            model.log.debug('-' * 80)
            model.log.debug(nsm)
            model.log.debug("nsm_type=%r value=%s" % (nsm_type, nsm_value))

        divide_by_sum = False
        if nsm.type in ['NSML1', 'NSML']:
            divide_by_sum = True

        if nsm.type == 'NSML1':
            if nsm_type == 'PSHELL': # area
                mass = _get_nsml1_prop(
                    model, nsm, nsm_type, nsm_value,
                    area_eids_pids, areas, nsm_centroids_area,
                    mass, cg, I, reference_point, is_area=True, debug=debug)
            elif nsm_type in ['PBAR', 'PBEAM', 'PROD', 'PTUBE']:
                mass = _get_nsml1_prop(
                    model, nsm, nsm_type, nsm_value,
                    length_eids_pids, lengths, nsm_centroids_length,
                    mass, cg, I, reference_point, is_area=False, debug=debug)
            elif nsm_type in ['ELEMENT', 'CONROD']:
                if len(nsm.ids) == 1 and nsm.ids[0] == 'ALL':
                    if nsm_type == 'CONROD':
                        nsm_ids = model._type_to_id_map[nsm_type]
                    else:
                        nsm_ids = list(model.elements.keys())
                else:
                    nsm_ids = nsm.ids
                #eids_pids = length_eids_pids[nsm_type]
                #print('nsm_type=%s eids_pids=%s' % (nsm_type, eids_pids))
                #if len(eids_pids) == 0:
                    #model.log.warning('  *skipping because there are no elements '
                                      #'associated with:\n%s' % str(nsm))
                    #continue

                mass = _nsm1_element(
                    model, nsm, nsm_ids,
                    all_eids_pids, area_length, nsm_centroids,
                    mass, cg, I, reference_point, is_area_array,
                    divide_by_sum, debug=debug)
            else:
                raise NotImplementedError(nsm_type)

        elif nsm.type in ['NSM1', 'NSML', 'NSM']:
            if nsm_type == 'PSHELL': # area
                pids = nsm.ids
                if debug:  # pragma: no cover
                    model.log.debug(nsm.rstrip())
                eids_pids = area_eids_pids[nsm_type]
                if len(eids_pids) == 0:
                    model.log.warning('  *skipping because there are no elements '
                                      'associated with:\n%s' % str(nsm))
                    continue

                area_all = areas[nsm_type]
                all_eids = eids_pids[:, 0]
                all_pids = eids_pids[:, 1]

                is_area = True
                if len(pids) == 1 and pids[0] == 'ALL':
                    #model.log.warning('  *skipping %s/PSHELL/ALL\n%s' % (nsm.type, str(nsm)))
                    centroidsi = nsm_centroids_area[nsm_type]
                    mass = _combine_prop_weighted_area_length_simple(
                        model, all_eids, area_all, centroidsi,
                        nsm_value, reference_point, mass, cg, I,
                        is_area, divide_by_sum,
                        debug=debug)
                else:
                    for pid in pids:
                        assert isinstance(pid, int), 'pid=%s type=%s' % (pid, type(pid))
                        ieidsi = np.where(all_pids == pid)
                        eidsi = all_eids[ieidsi]
                        centroidsi = nsm_centroids_area[nsm_type][ieidsi]
                        areasi = area_all[ieidsi]
                        if len(centroidsi) != len(eidsi):
                            msg = 'ncentroids=%s neids=%s' % (len(centroidsi), len(eidsi))
                            raise RuntimeError(msg)

                        if debug:  # pragma: no cover
                            #print('eids = %s' % all_eids)
                            model.log.debug('  eidsi = %s' % eidsi)
                            model.log.debug('  nsm_centroids_area = %s' % centroidsi)
                            model.log.debug('  centroidsi = %s' % centroidsi)

                        mass = _combine_prop_weighted_area_length_simple(
                            model, eidsi, areasi, centroidsi,
                            nsm_value, reference_point, mass, cg, I,
                            is_area, divide_by_sum,
                            debug=debug)
            elif nsm_type in ['PBAR', 'PBEAM', 'PROD', 'PTUBE']:
                length_all = np.array(lengths[nsm_type])
                pids = nsm.ids
                eids_pids = length_eids_pids[nsm_type]
                if len(eids_pids) == 0:
                    model.log.debug('  *skipping because there are no elements'
                                    ' associated with:\n%s' % str(nsm))
                    continue

                length_all = np.array(lengths[nsm_type])
                all_eids = eids_pids[:, 0]
                all_pids = eids_pids[:, 1]
                is_area = False

                nsm_centroidsi = nsm_centroids_length[nsm_type]
                if len(pids) == 1 and pids[0] == 'ALL':
                    lengthsi = length_all
                    centroidsi = nsm_centroidsi
                    mass = _combine_prop_weighted_area_length_simple(
                        model, eidsi, lengthsi, centroidsi,
                        nsm_value, reference_point, mass, cg, I,
                        is_area, divide_by_sum,
                        debug=debug)
                else:
                    for pid in pids:
                        assert isinstance(pid, int), 'pid=%s type=%s' % (pid, type(pid))
                        ieidsi = np.where(all_pids == pid)
                        eidsi = all_eids[ieidsi]
                        centroidsi = nsm_centroidsi[ieidsi]
                        lengthsi = length_all[ieidsi]
                        if len(centroidsi) != len(eidsi):
                            msg = 'ncentroids=%s neids=%s' % (len(centroidsi), len(eidsi))
                            raise RuntimeError(msg)

                        if debug:  # pragma: no cover
                            model.log.debug('  eidsi = %s' % eidsi)
                            model.log.debug('  nsm_centroids_lengthi = %s' % centroidsi)
                            model.log.debug('  centroidsi = %s' % centroidsi)

                        mass = _combine_prop_weighted_area_length_simple(
                            model, eidsi, lengthsi, centroidsi,
                            nsm_value, reference_point, mass, cg, I,
                            is_area, divide_by_sum,
                            debug=debug)
            elif nsm_type in ['ELEMENT', 'CONROD']:
                if len(nsm.ids) == 1 and nsm.ids[0] == 'ALL':
                    if nsm_type == 'CONROD':
                        nsm_ids = model._type_to_id_map[nsm_type]
                    else:
                        nsm_ids = list(model.elements.keys())
                else:
                    nsm_ids = nsm.ids

                mass = _nsm1_element(
                    model, nsm, nsm_ids,
                    all_eids_pids, area_length, nsm_centroids,
                    mass, cg, I, reference_point, is_area_array,
                    divide_by_sum, debug=debug)
            else:
                raise NotImplementedError(nsm_type)
        else:
            model.log.warning('skipping %s\n%s' % (nsm.type, str(nsm)))


    #print('area:')
    #for ptype, eids_pids in sorted(iteritems(area_eids_pids)):
        #eids = eids_pids[:, 0]
        #pids = eids_pids[:, 1]
        #area = np.array(areas[ptype])
        #ieids = np.argsort(eids)
        #eids_sorted = eids[ieids]
        #area_sorted = area[ieids]
        #print('  ', ptype, eids_sorted, area_sorted)

    #print('length:')
    #for ptype, length_eid in sorted(iteritems(length_eids_pids)):
        #eids = np.array(length_eid, dtype='int32')
        #length = np.array(lengths[ptype])
        #print('  ', ptype, eids, length)
    return mass

def _get_nsml1_prop(
        model, nsm, nsm_type, nsm_value,
        area_eids_pids, areas, nsm_centroids_area,
        mass, cg, I, reference_point, is_area=True, debug=True):
    if is_area:
        word = 'area'
        key_map = {
            'PSHELL' : ['PSHELL', 'PCOMP', 'PCOMPG'],
            'PCOMP' : ['PSHELL', 'PCOMP', 'PCOMPG'],
            'PCOMPG' : ['PSHELL', 'PCOMP', 'PCOMPG'],
        }
    else:
        word = 'length'
        key_map = {
            'PBAR' : ['PBAR', 'PBARL'],
            'PBEAM' : ['PBEAM', 'PBEAML', 'PBCOMP'],
            'PROD' : ['PROD'],
        }
    keys = key_map[nsm_type]

    eids_pids = area_eids_pids[nsm_type]
    area_all = areas[nsm_type]
    if len(eids_pids) == 0:
        model.log.warning('  skipping because there are no elements'
                          ' associated with:\n%s' % str(nsm))
        return mass

    #all_eids = eids_pids[:, 0]
    all_pids = eids_pids[:, 1]
    if len(nsm.ids) == 1 and nsm.ids[0] == 'ALL':
        ids = np.hstack([model._type_to_id_map[key]
                         for key in keys if key in model._type_to_id_map])
    else:
        assert 'ALL' not in nsm.ids, str(nsm)
        ids = np.array(nsm.ids, dtype='int32')

    pids_to_apply = all_pids
    upids = np.unique(pids_to_apply)
    pids_to_apply = np.intersect1d(upids, ids)

    if debug:  # pragma: no cover
        model.log.debug("  all_pids = %s" % all_pids)
        model.log.debug("  nsm_pids = %s" % ids)
        model.log.debug("  pids_to_apply = %s" % pids_to_apply)
    assert len(pids_to_apply) > 0, pids_to_apply

    area_sum = 0.
    areas_ipids = []
    for upid in pids_to_apply:
        ipid = np.where(all_pids == upid)[0]
        #print('ipid =', ipid)
        eids = eids_pids[ipid, 0]
        area = area_all[ipid]

        #eids_actual = eids[ipid]
        #area_actual = area[ipid]
        if debug:  # pragma: no cover
            model.log.debug('  eids = %s' % eids)
            model.log.debug('  %s = %s' % (word, area))
        area_sum += area.sum()
        areas_ipids.append((area, ipid))

    if debug:  # pragma: no cover
        model.log.debug("%s_sum = %s" % (word, area_sum))
    nsm_centroidsi = nsm_centroids_area[nsm_type]

    mass = _combine_prop_weighted_area_length(
        model, areas_ipids, nsm_centroidsi,
        is_area, area_sum,
        nsm_value, reference_point, mass, cg, I,
        debug=debug)
    return mass

def _nsm1_element(model, nsm, nsm_ids, all_eids_pids, area_length, nsm_centroids,
                  mass, cg, I, reference_point, is_area_array,
                  divide_by_sum, debug=False):
    """calculates the mass of an NSM1 element"""
    nsm_value = nsm.value
    #model.log.warning('  *skipping NSM1/ELEMENT\n%s' % str(nsm))
    #print(nsm.rstrip())
    eids = all_eids_pids[:, 0]
    ids = np.array(nsm_ids, dtype='int32')
    if debug:  # pragma: no cover
        model.log.debug('  ids = %s' % ids)
        model.log.debug('  eids = %s' % eids)
        model.log.debug('  is_area_array = %s' % is_area_array)

    isort = np.searchsorted(eids, ids)

    eids_pids = all_eids_pids
    #area = area_length[is_area]
    #length = area_length[~is_area]
    if debug:  # pragma: no cover
        model.log.debug('  area_length = %s' % area_length)
    #print('  area =', area)
    #print('  length =', length)
    #area_length =
    if debug:  # pragma: no cover
        model.log.debug(nsm.nsm_type)
        model.log.debug(eids_pids)
    #pids = all_eids_pids[:, 1]

    #print('  pids =', pids)
    #print('  area =', area)
    #print('  length =', length)

    ipassed = isort != len(eids)
    if debug:  # pragma: no cover
        model.log.debug('  isort_1 = %s' % isort)
        model.log.debug('  ipassed = %s' % ipassed)

    isort = isort[ipassed]
    if len(isort) == 0:
        model.log.warning('  *no ids found')
        return mass

    if debug:  # pragma: no cover
        model.log.debug('  isort_2 =' % isort)
        model.log.debug('  eids[isort] =' % eids[isort])

    iwhere = eids[isort] == ids
    eids_actual = eids[isort][iwhere]
    area_length_actual = area_length[isort][iwhere]
    is_area_actual = is_area_array[isort][iwhere]
    if len(np.unique(is_area_actual)) != 1:
        model.log.error('  eids = %s' % eids_actual)
        model.log.error('  area_length_actual = %s' % area_length_actual)
        model.log.error('  is_area_actual = %s' % is_area_actual)
        msg = 'Mixed Line/Area element types for:\n%s' % str(nsm)
        for eid in eids_actual:
            msg += str(model.elements[eid])
        raise RuntimeError(msg)

    is_area = is_area_actual[0]
    if debug:  # pragma: no cover
        #print('  is_area_actual =', is_area_actual)
        if is_area:
            model.log.debug('  area!')
        else:
            model.log.debug('  length!')
    nsm_centroid = nsm_centroids[isort, :][iwhere, :]

    # this is area or length depending on eid type
    cgi = area_length_actual[:, np.newaxis] * nsm_centroid

    if debug:  # pragma: no cover
        model.log.debug('  nsm_centroid = %s' % nsm_centroid)
        model.log.debug('  area_length_actual = %s' % area_length_actual)
        model.log.debug('  cgi = %s' % cgi)

    #if is_area:
        #word = 'area'
    #else:
        #word = 'length'

    if divide_by_sum:
        area_sum = area_length_actual.sum()
        #area_sum_str = '%s_sum=%s ' % (word, area_sum)
        area_length_actual2 = area_length_actual / area_sum
    else:
        #area_sum = 1.
        #area_sum_str = ''
        area_length_actual2 = area_length_actual

    for eid, area_lengthi, centroid in zip(eids_actual, area_length_actual2, nsm_centroid):
        massi = nsm_value * area_lengthi
        #if debug:  # pragma: no cover
            #print('  eid=%s %si=%s %snsm_value=%s mass=%s' % (
                #eid, word, area_lengthi, area_sum_str, nsm_value, massi))
        mass = _increment_inertia(centroid, reference_point, massi, mass, cg, I)
    return mass

def _apply_mass_symmetry(model, sym_axis, scale, mass, cg, inertia):
    """
    Scales the mass & moement of inertia based on the symmetry axes
    and the PARAM WTMASS card
    """
    if isinstance(sym_axis, string_types):
        sym_axis = [sym_axis]
    elif isinstance(sym_axis, (list, tuple)):
        # basically overwrite the existing values on the AERO/AEROS card
        pass
    else:
        sym_axis = []

        # The symmetry flags on the AERO/AEROS must be the same, so
        # it doesn't matter which we one pick.  However, they might
        # not both be defined.
        #
        # Anti-symmetry refers to load, not geometry.  Geometry is
        # always symmetric.
        #
        if model.aero is not None:
            if model.aero.is_symmetric_xy or model.aero.is_anti_symmetric_xy:
                sym_axis.append('xy')
            if model.aero.is_symmetric_xz or model.aero.is_anti_symmetric_xz:
                sym_axis.append('xz')

        if model.aeros is not None:
            if model.aeros.is_symmetric_xy or model.aeros.is_anti_symmetric_xy:
                sym_axis.append('xy')
            if model.aeros.is_symmetric_xz or model.aeros.is_anti_symmetric_xz:
                sym_axis.append('xz')

    sym_axis = list(set(sym_axis))
    short_sym_axis = [sym_axisi.lower() for sym_axisi in sym_axis]
    is_no = 'no' in short_sym_axis
    if is_no and len(short_sym_axis) > 1:
        raise RuntimeError('no can only be used by itself; sym_axis=%s' % (str(sym_axis)))
    for sym_axisi in sym_axis:
        if sym_axisi.lower() not in ['no', 'xy', 'yz', 'xz']:
            msg = 'sym_axis=%r is invalid; sym_axisi=%r; allowed=[no, xy, yz, xz]' % (
                sym_axis, sym_axisi)
            raise RuntimeError(msg)

    if sym_axis:
        # either we figured sym_axis out from the AERO cards or the user told us
        model.log.debug('Mass/MOI sym_axis = %r' % sym_axis)

        if 'xz' in sym_axis:
            # y intertias are 0
            cg[1] = 0.0
            mass *= 2.0
            inertia[0] *= 2.0
            inertia[1] *= 2.0
            inertia[2] *= 2.0
            inertia[3] *= 0.0  # Ixy
            inertia[4] *= 2.0  # Ixz; no y
            inertia[5] *= 0.0  # Iyz

        if 'xy' in sym_axis:
            # z intertias are 0
            cg[2] = 0.0
            mass *= 2.0
            inertia[0] *= 2.0
            inertia[1] *= 2.0
            inertia[2] *= 2.0
            inertia[3] *= 2.0  # Ixy; no z
            inertia[4] *= 0.0  # Ixz
            inertia[5] *= 0.0  # Iyz

        if 'yz' in sym_axis:
            # x intertias are 0
            cg[0] = 0.0
            mass *= 2.0
            inertia[0] *= 2.0
            inertia[1] *= 2.0
            inertia[2] *= 2.0
            inertia[3] *= 0.0  # Ixy
            inertia[4] *= 0.0  # Ixz
            inertia[5] *= 2.0  # Iyz; no x

    if scale is None and 'WTMASS' in model.params:
        param = model.params['WTMASS']
        #assert isinstance(param, PARAM), 'param=%s' % param
        scale = param.values[0]
        if scale != 1.0:
            model.log.info('WTMASS scale = %r' % scale)
    elif scale is None:
        scale = 1.0
    mass *= scale
    inertia *= scale
    return (mass, cg, inertia)

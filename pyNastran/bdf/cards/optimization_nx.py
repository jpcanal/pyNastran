"""
All optimization cards are defined in this file.  This includes:

* dconstrs - DCONSTR
* dconadds - DCONADD
* ddvals - DDVAL
* dlinks - DLINK
* dresps - DRESP1, DRESP2, DRESP3
* dscreen - DSCREEN
* dvgrids - DVGRID
* desvars - DESVAR
* dvcrels - DVCREL1, DVCREL2
* dvmrels - DVMREL1, DVMREL2
* dvprels - DVPREL1, DVPREL2
* doptprm - DOPTPRM

some missing optimization flags
http://mscnastrannovice.blogspot.com/2014/06/msc-nastran-design-optimization-quick.html"""
# pylint: disable=C0103,R0902,R0904,R0914
from __future__ import annotations
from typing import TYPE_CHECKING
#from itertools import cycle, count
import numpy as np

from pyNastran.utils.numpy_utils import integer_types, float_types
from pyNastran.bdf.field_writer_8 import set_blank_if_default
from pyNastran.bdf.cards.base_card import (
    BaseCard, expand_thru_by, break_word_by_trailing_integer,
    break_word_by_trailing_parentheses_integer_ab)
    #collapse_thru_by_float, condense, build_thru_float)
from pyNastran.bdf.cards.optimization import OptConstraint, DVXREL1, get_dvxrel1_coeffs
from pyNastran.bdf.bdf_interface.assign_type import (
    integer, integer_or_blank, integer_or_string, integer_string_or_blank,
    double, double_or_blank, string, string_or_blank,
    integer_double_or_blank, integer_double_string_or_blank,
    double_string_or_blank, interpret_value, check_string, loose_string)
from pyNastran.bdf.field_writer_8 import print_card_8
from pyNastran.bdf.field_writer_16 import print_card_16
from pyNastran.bdf.field_writer_double import print_card_double
from pyNastran.bdf.cards.utils import build_table_lines
if TYPE_CHECKING:  # pragma: no cover
    from pyNastran.bdf.bdf import BDF

#TODO: replace this with formula
valid_pcomp_codes = [3, #3-z0
                     #'Z0',
                     # 13-t1, 14-theta1, 17-t2, 18-theta2
                     13, 14, 17, 18,
                     23, 24, 27, 28,
                     33, 34, 37, 38,
                     43, 44, 47, 48,
                     53, 54, 57, 58,
                     63, 64, 67, 68]

def validate_dvcrel(validate, element_type, cp_name):
    """
    Valdiates the DVCREL1/2

    .. note:: words that start with integers (e.g., 12I/T**3) doesn't
              support strings

    """
    if not validate:
        return
    msg = 'DVCRELx: element_type=%r cp_name=%r is invalid' % (element_type, cp_name)
    if element_type == 'CMASS4':
        options = ['M']
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CELAS4':
        options = ['K']
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type in ['CQUAD4']:
        options = ['T1', 'T2', 'T3', 'T4'] # 'ZOFFS',
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CTRIA3':
        options = ['T1', 'T2', 'T3']
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CONM2':
        options = ['M', 'X1', 'X2', 'X3']
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CBAR':
        options = ['X1', 'X2', 'X3', 'W1A', 'W2A', 'W3A', 'W1B', 'W2B', 'W3B']
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CBEAM':
        options = ['X1', 'X2', 'X3']
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type in ['CELAS1']:
        options = []
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type in ['CBUSH']:
        options = ['X1', 'X2', 'X3', 'S', 'S1', 'S2', 'S3']
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CVISC':
        options = []
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CGAP':
        options = []
        _check_dvcrel_options(cp_name, element_type, options)
    elif element_type == 'CBUSH1D':
        options = []
        _check_dvcrel_options(cp_name, element_type, options)
    else:
        raise NotImplementedError(msg)


def _check_dvcrel_options(cp_name, element_type, options):
    if cp_name not in options:
        soptions = [str(val) for val in options]
        msg = (
            '%r is an invalid option for %s\n'
            'valid: [%s]' % (cp_name, element_type, ', '.join(soptions)))
        raise ValueError(msg)

class DMNCON(OptConstraint):
    """
    | DMNCON | ID | SYMC |    |       |    |    |
    |        |  X |   Y  | Z  |   N1  | N2 | N3 |
    |        | M1 |  M2  | M3 | NSECT |    |    |
    | DMNCON | ID | SYMP |    |       |    |    |
    |        |  X |   Y  | Z  |   N1  | N2 | N3 |
    DMNCON         1    SYMP
              0.      0.      0.      0.      1.      0.
    """
    type = 'DMNCON'

    #@classmethod
    #def _init_from_empty(cls):
        #rtype = 'DISP'
        #return DSCREEN(rtype, trs=-0.5, nstr=20, comment='')

    def __init__(self, constraint_id: int, constraint_type: str,
                 xyz, normal, comment=''):
        """
        Creates a DMNCON object

        Parameters
        ----------
        self.constraint_id = constraint_id
        self.constraint_type = constraint_type
        self.xyz = xyz
        self.normal = normal
        comment : str; default=''
            a comment for the card

        """
        OptConstraint.__init__(self)
        if comment:
            self.comment = comment

        self.constraint_id = constraint_id
        self.constraint_type = constraint_type
        self.xyz = xyz
        self.normal = normal

    @classmethod
    def add_card(cls, card, comment=''):
        """
        Adds a DMNCON card from ``BDF.add_card(...)``

        Parameters
        ----------
        card : BDFCard()
            a BDFCard object
        comment : str; default=''
            a comment for the card

        """
        constraint_id = integer(card, 1, 'constraint_id')
        constraint_type = string(card, 2, 'constraint_id')
        if constraint_type == 'SYMP':
            xyz = np.array([
                double_or_blank(card, 9, 'x', default=0.),
                double_or_blank(card, 10, 'y', default=0.),
                double_or_blank(card, 11, 'z', default=0.),
            ])
            normal = np.array([
                double_or_blank(card, 12, 'n1', default=0.),
                double_or_blank(card, 13, 'n2', default=0.),
                double_or_blank(card, 14, 'n3', default=0.),
            ])
            assert len(card) <= 15, f'len(DMNCON card) = {len(card):d}\ncard={card}'
        else:
            raise NotImplementedError(constraint_type)
        return DMNCON(constraint_id, constraint_type, xyz, normal, comment=comment)

    def raw_fields(self):
        list_fields = ['DMNCON', self.constraint_id, self.constraint_type, None, None, None, None, None, None]

        if self.constraint_type == 'SYMP':
            list_fields.extend([self.xyz[0], self.xyz[1], self.xyz[2],
                                self.normal[0], self.normal[1], self.normal[2]])
        else:
            raise NotImplementedError(self.constraint_type)
        return list_fields

    def repr_fields(self):
        list_fields = self.raw_fields()
        return list_fields

    def write_card(self, size: int=8, is_double: bool=False) -> str:
        card = self.repr_fields()
        if size == 8:
            return self.comment + print_card_8(card)
        if is_double:
            return self.comment + print_card_double(card)
        return self.comment + print_card_16(card)

class GROUP(OptConstraint):
    """
    +-------+-------+-----------------------------------+
    | GROUP |  10   | Assembly AA4                      |
    +-------+-------+-----------------------------------+
    |       | META  | 100 RPM                           |
    +-------+-------+-----------------------------------+
    |       | META  | Optionally continue the meta data |
    +-------+-------+-----+------+-----+----+---+---+---+
    |       | GRID  |  1  |   2  |  3  |  4 | 5 | 6 | 7 |
    +-------+-------+-----+------+-----+----+---+---+---+
    |       |       |  8  |      |     |    |   |   |   |
    +-------+-------+-----+------+-----+----+---+---+---+
    |       | GRID  | 10  | THRU | 20  |    |   |   |   |
    +-------+-------+-----+------+-----+----+---+---+---+
    |       | GRID  | 100 | THRU | 200 |    |   |   |   |
    +-------+-------+-----+------+-----+----+---+---+---+
    |       | GRID  | 341 | THRU | 360 | BY | 2 |   |   |
    +-------+-------+-----+------+-----+----+---+---+---+
    |       | ELEM  | 30  | THRU | 40  |    |   |   |   |
    +-------+-------+-----+------+-----+----+---+---+---+
    |       | PROP  | ALL |      |     |    |   |   |   |
    +-------+-------+-----+------+-----+----+---+---+---+
    """
    type = 'GROUP'

    #@classmethod
    #def _init_from_empty(cls):
        #rtype = 'DISP'
        #return DSCREEN(rtype, trs=-0.5, nstr=20, comment='')

    def __init__(self, group_id: int,
                 nodes, elements, properties, comment=''):
        """
        Creates a GROUP object

        Parameters
        ----------
        group_id : int
            Group identification number
        meta : List[str]
            Optional character data to store with the group definition.
            META can be continued on multiple continuation lines.
            The META keyword in the 2nd field must appear on every line
            where metadata is entered.
        group_type : str
            Designates the type of IDs defined in a specific row, or in
            a set of rows. Multiple TYPE can exist on the same GROUP entry.
            Allowed types:
            - GRID: Designates the row includes grid point IDs.
            - ELEM: Designates the row includes element IDs.
            - PROP: Designates the row includes property IDs.
        comment : str; default=''
            a comment for the card

        """
        OptConstraint.__init__(self)
        if comment:
            self.comment = comment

        self.group_id = group_id
        self.nodes = nodes
        self.elements = elements
        self.properties = properties

    @classmethod
    def add_card(cls, card, comment=''):
        """
        Adds a GROUP card from ``BDF.add_card(...)``

        Parameters
        ----------
        card : BDFCard()
            a BDFCard object
        comment : str; default=''
            a comment for the card

        """
        group_id = integer(card, 1, 'group_id')
        #assert len(card) <= 4, f'len(GROUP card) = {len(card):d}\ncard={card}'
        i = 9
        nodes = []
        elements = []
        properties = []
        nfields = len(card)
        while i < nfields:
            name = string_or_blank(card, i, 'name', default=None)
            if name in ['GRID', 'ELEM', 'PROP']:
                j = 1
                #i9 = i + 9
                values = []
                i += 1
                while i < nfields:
                    namei = name + str(j)
                    #print(card[i])
                    value = integer_string_or_blank(card, i, namei)
                    if isinstance(value, int):
                        values.append(value)
                    elif value is None:
                        pass
                    elif isinstance(value, str):
                        assert value in ['GRID', 'ELEM', 'PROP', 'META'], value
                        #print(f'breaking on {value}')
                        break
                    else:
                        print(value)
                        asdf
                    i += 1
                    j += 1
            else:
                raise NotImplementedError(name)
            if name == 'GRID':
                nodes.append(values)
            elif name == 'ELEM':
                elements.append(values)
            elif name == 'PROP':
                properties.append(values)
            else:
                raise NotImplementedError(name)
        return GROUP(group_id, nodes, elements, properties, comment=comment)

    def raw_fields(self):
        list_fields = ['GROUP', self.group_id]
        return list_fields


    def _write_groupi(self, name: str, elem: List[int], list_fields):
        elem0 = elem[:7]
        list_fields.extend([name] + elem0)
        i = len(elem0)
        #print(name, i)
        while i < len(elem):
            list_fields.extend([None] + elem[i:i+7])
            i += 7
            #if i > 20:
                #break
        nleftover = i % 7
        if nleftover != 0:
            n_none = 7 - nleftover
            #print(f' adding {n_none} Nones')
            list_fields.extend([None] * n_none)

    def repr_fields(self):
        list_fields = ['GROUP', self.group_id, None, None, None, None,
                       None, None, None]

        for node in self.nodes:
            self._write_groupi('GRID', node, list_fields)
        for elem in self.elements:
            self._write_groupi('ELEM', elem, list_fields)
        for prop in self.properties:
            self._write_groupi('PROP', prop, list_fields)
        return list_fields

    def write_card(self, size: int=8, is_double: bool=False) -> str:
        card = self.repr_fields()
        if size == 8:
            return self.comment + print_card_8(card)
        if is_double:
            return self.comment + print_card_double(card)
        return self.comment + print_card_16(card)



class DVTREL1(BaseCard):
    """
    +---------+--------+--------+--------+-------+--------+--------+-----+
    |   1     |    2   |   3    |    4   |   5   |    6   |   7    |  8  |
    +=========+========+========+========+=======+========+========+=====+
    | DVTREL1 |   ID   | LABEL  |  GRPID | STATE | DSVFLG |        |     |
    +---------+--------+--------+--------+-------+--------+--------+-----+
    |         |  DVID1 |        |        |       |        |        |     |
    +---------+--------+--------+--------+-------+--------+--------+-----+
    """
    type = 'DVTREL1'

    #@classmethod
    #def _init_from_empty(cls):
        #oid = 1
        #prop_type = 'PSHELL'
        #pid = 1
        #pname_fid = 'T'
        #dvids = [1]
        #coeffs = [1.]
        #return DVTREL1(oid, prop_type, pid, pname_fid, dvids, coeffs,
                       #p_min=None, p_max=1e20, c0=0.0,
                       #validate=False)

    def __init__(self, dvtrel_id: int, label: str, group_id: int,
                 state: str='ACTIVE', dsv_flag: int=0, dvid1: int=0,
                 validate=False, comment: str=''):
        """
        Creates a DVTREL1 card

        Parameters
        ----------
        dvtrel_id : int
            Identification number of DVTREL1 entry
        label : str
            Optional user-defined label
        group_id : int
            ID of a GROUP bulk entry that specifies a list of elements.
            The software associates the following types of elements with
            topology optimization:
            - 3D solid elements CHEXA, CPENTA, CPYRAM, CTETRA
            - shell elements CTRIA3, CTRIA6. CTRIAR, CQUAD4, CQUAD8, CQUADR.
            Any other element types or IDs for non-existent elements listed
            on a GROUP entry are ignored. (Integer>0)
        state : str; default='ACTIVE'
            Specifies that the elements referenced in the GRPID field are
            either ACTIVE or FROZEN. The software modifies the active elements,
            but not the frozen elements.
        dsv_flag: int; default=0
            Flag set by the software when you are recycling design variables
            from a previous solution for restart purposes. (Integer=0 or 1)
            dsv_flag=0 or blank (Default):
                Value used in a first pass optimization solution. This value
                triggers the software to create new design variables and other
                relevant data for the elements designated as ACTIVE.
            dsv_flag=1: Value used in a restart solution. This value triggers
                the software to use already existing design variables and their
                values created in a previous solution. Normally, the software
                sets this value of 1 for dsv_flag automatically when writing the
                updated bulk data into the punch file.
        dvid1: int; default=0
            Option to control the identification numbers for the
            auto-generated design variables. (Integer≥0)
            DVID1=0 or blank (Default):
                the design variable IDs will be equal to the IDs of the
                associated elements plus an automatically calculated
        validate : bool; default=False
            should the card be validated
        comment : str; default=''
            a comment for the card

        """
        BaseCard.__init__(self)
        self.dvtrel_id = dvtrel_id
        self.label = label
        self.group_id = group_id
        self.state = state
        self.dvid1 = dvid1
        self.dsv_flag = dsv_flag
        self.group_id_ref = None

    @classmethod
    def add_card(cls, card, comment=''):
        """
        Adds a DVTREL1 card from ``BDF.add_card(...)``

        Parameters
        ----------
        card : BDFCard()
            a BDFCard object
        comment : str; default=''
            a comment for the card

        """
        dvtrel_id = integer(card, 1, 'dvtrel_id')
        label = string_or_blank(card, 2, 'label', default='')
        group_id = integer(card, 3, 'group_id')
        state = string_or_blank(card, 4, 'state', default='ACTIVE')
        dsv_flag = integer_or_blank(card, 5, 'dsv_flag', default=0)
        dvid1 = integer_or_blank(card, 8, 'dsv_flag', default=0)

        return DVTREL1(dvtrel_id, label, group_id, state=state,
                       dsv_flag=dsv_flag, dvid1=dvid1,
                       comment=comment)

    def _verify(self, xref):
        """
        Verifies all methods for this object work

        Parameters
        ----------
        xref : bool
            has this model been cross referenced

        """
        pass

    def OptID(self):
        return self.dvtrel_id

    #def cross_reference(self, model: BDF) -> None:
        #"""
        #Cross links the card so referenced cards can be extracted directly

        #Parameters
        #----------
        #model : BDF()
            #the BDF object
        #"""
        #msg = ', which is required by DVTREL1 oid=%r' % self.oid
        #self.pid_ref = self._get_property(model, self.pid, msg=msg)
        #self.dvids_ref = [model.Desvar(dvid, msg) for dvid in self.dvids]

    #def uncross_reference(self) -> None:
        #"""Removes cross-reference links"""
        #self.pid = self.Pid()
        #self.pid_ref = None
        #self.dvids = self.desvar_ids
        #self.dvids_ref = None

    def raw_fields(self):
        list_fields = ['DVTREL1', self.dvtrel_id, self.label, self.group_id, self.state,
                       self.dsv_flag, None, None, None, self.dvid1]
        return list_fields

    def repr_fields(self):
        return self.raw_fields()
        return list_fields

    def write_card(self, size: int=8, is_double: bool=False) -> str:
        card = self.repr_fields()
        if size == 8:
            return self.comment + print_card_8(card)
        return self.comment + print_card_16(card)



"""
src/services/text_cleaning_service.py
Advanced Text Cleaning, Multi-Discipline Engineering Dictionary, Domain-Safe Spell Correction,
Comment Action Segmentation, Reviewer Attribution, and Semantic Duplicate Detection Engine.
"""

import re
import difflib
import time
from typing import List, Dict, Any, Tuple, Optional, Set
import textdistance

from src.core.dtos.comment_processing_dtos import (
    CleanedCommentDTO,
    CorrectionDTO,
    TextCleaningResultDTO
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class TextCleaningService:
    """
    NLP & Text Intelligence Engine for engineering reviewer markup text.
    Provides multi-discipline acronym expansion, domain-safe spell correction,
    OCR noise suppression, multi-action segmentation, reviewer attribution,
    priority scoring, and cross-drawing semantic duplicate detection.
    """

    def __init__(self, expand_acronyms: bool = True):
        self.expand_acronyms = expand_acronyms
        self.engineering_dict = self._build_engineering_dictionary()
        self.discipline_taxonomies = self._build_discipline_taxonomies()
        self.known_typos = self._build_known_typos_map()
        self._standard_vocab = self._build_standard_vocab()
        self.action_verbs = self._build_action_verbs_set()
        self.vocabulary = self._build_comprehensive_vocabulary()
        self.vocab_lookup = {word.upper(): word for word in self.vocabulary}
        
        self.high_priority_keywords = {
            "DO NOT", "INCORRECT", "WRONG", "CRITICAL", "SAFETY", 
            "CONFLICTING", "MUST", "ERROR", "HOLD", "STOP", "FAIL", "REJECT"
        }
        self.medium_priority_keywords = {
            "VERIFY", "CONFIRM", "UPDATE", "REVISE", "CHECK", "ROTATE", 
            "ADD", "INDICATE", "CLARIFY", "MATCH", "SWITCH", "LOCATE", "REFERENCE"
        }
        self.low_priority_keywords = {
            "FOR INFORMATION ONLY", "NOTE:", "NOTE", "SIMILAR TO", "FYI", "TYPICAL", "AS-BUILT"
        }

    # =========================================================================
    # 1. DICTIONARIES & TAXONOMIES
    # =========================================================================

    def _build_engineering_dictionary(self) -> Dict[str, str]:
        """
        Unambiguous multi-discipline engineering acronym dictionary.
        Only contains distinct, non-conflicting multi-letter acronyms.
        Common English words (BAR, SO, AIR, PL, BL, EXP, PE, CW, HW, BM, GL)
        are deliberately excluded to avoid corrupting standard reviewer comments.
        """
        return {
            # Drawing & General Documentation
            'DWG': 'Drawing',
            'REV': 'Revision',
            'REQD': 'Required',
            "REQ'D": 'Required',
            'QTY': 'Quantity',
            'DIA': 'Diameter',
            'THK': 'Thickness',
            'MIN': 'Minimum',
            'MAX': 'Maximum',
            'ELEV': 'Elevation',
            'COORD': 'Coordinate',
            'SPECS': 'Specifications',
            'DTL': 'Detail',
            'SECT': 'Section',
            'CTR': 'Center',
            'REF': 'Reference',

            # Piping & Process
            'P&ID': 'Piping and Instrumentation Diagram',
            'P&I': 'Piping and Instrumentation',
            'PFD': 'Process Flow Diagram',
            'BOM': 'Bill of Materials',
            'MTO': 'Material Take-Off',
            'NPS': 'Nominal Pipe Size',
            'DN': 'Diameter Nominal',
            'PN': 'Pressure Nominal',
            'SCH': 'Schedule',
            'SS316L': 'Stainless Steel 316L',
            'SS304': 'Stainless Steel 304',
            'CS': 'Carbon Steel',
            'PSV': 'Pressure Safety Valve',
            'PRV': 'Pressure Relief Valve',
            'ESD': 'Emergency Shutdown',
            'HAZOP': 'Hazard and Operability Study',
            'SIL': 'Safety Integrity Level',
            'FLG': 'Flange',
            'BW': 'Butt Weld',
            'SW': 'Socket Weld',
            'THD': 'Threaded',
            'NPT': 'National Pipe Taper',
            'RF': 'Raised Face',
            'FF': 'Flat Face',
            'RTJ': 'Ring Type Joint',
            'WN': 'Weld Neck',
            'FEED': 'Front End Engineering Design',
            'EPC': 'Engineering Procurement Construction',
            'MOC': 'Management of Change',

            # Mechanical & HVAC
            'GA': 'General Arrangement',
            'ISO': 'Isometric',
            'DIM': 'Dimension',
            'TOL': 'Tolerance',
            'HVAC': 'Heating Ventilation and Air Conditioning',
            'CFM': 'Cubic Feet per Minute',
            'BHP': 'Brake Horsepower',
            'RPM': 'Revolutions Per Minute',
            'GPM': 'Gallons Per Minute',
            'AHU': 'Air Handling Unit',
            'FCU': 'Fan Coil Unit',
            'VAV': 'Variable Air Volume',
            'CHW': 'Chilled Water',
            'PSI': 'Pounds per Square Inch',
            'PSIG': 'Pounds per Square Inch Gauge',
            'FPM': 'Feet Per Minute',
            'REF': 'Reference',
            'TYP': 'Typical',
            'SHT': 'Sheet',

            # Civil & Structural
            'HSS': 'Hollow Structural Section',
            'CL': 'Centerline',
            'EL': 'Elevation',
            'TOC': 'Top of Concrete',
            'BOS': 'Bottom of Steel',
            'TOS': 'Top of Steel',
            'FTG': 'Footing',
            'WF': 'Wide Flange',
            'FND': 'Foundation',
            'CJ': 'Construction Joint',
            'EJ': 'Expansion Joint',
            'REBAR': 'Reinforcing Bar',
            'FFL': 'Finished Floor Level',
            'SSL': 'Structural Slab Level',

            # Electrical & Instrumentation
            'I/O': 'Input Output',
            'PLC': 'Programmable Logic Controller',
            'DCS': 'Distributed Control System',
            'SCADA': 'Supervisory Control and Data Acquisition',
            'VFD': 'Variable Frequency Drive',
            'RTD': 'Resistance Temperature Detector',
            'JB': 'Junction Box',
            'NEMA': 'National Electrical Manufacturers Association',
            'GND': 'Ground',
            'MCC': 'Motor Control Center',
            'UPS': 'Uninterruptible Power Supply',
            'CT': 'Current Transformer',
            'PT': 'Potential Transformer',
            'DP': 'Differential Pressure',
            'FIT': 'Flow Indicating Transmitter',
            'LIT': 'Level Indicating Transmitter',
            'PIT': 'Pressure Indicating Transmitter',
            'TIT': 'Temperature Indicating Transmitter',
            'FCV': 'Flow Control Valve',
            'LCV': 'Level Control Valve',
            'PCV': 'Pressure Control Valve',
            'TCV': 'Temperature Control Valve',
            'SOV': 'Solenoid Operated Valve',

            # Quality, Codes & Standards
            'ASME': 'American Society of Mechanical Engineers',
            'AWS': 'American Welding Society',
            'API': 'American Petroleum Institute',
            'ASTM': 'American Society for Testing and Materials',
            'NFPA': 'National Fire Protection Association',
            'OSHA': 'Occupational Safety and Health Administration',
            'PPE': 'Personal Protective Equipment',
            'SOP': 'Standard Operating Procedure',
            'QA': 'Quality Assurance',
            'QC': 'Quality Control',
            'NDE': 'Non-Destructive Examination',
            'NDT': 'Non-Destructive Testing',
            'WPS': 'Welding Procedure Specification',
            'PQR': 'Procedure Qualification Record',
            'NACE': 'National Association of Corrosion Engineers',
            'MSS': 'Manufacturers Standardization Society',
            'ISA': 'International Society of Automation',
            'IEEE': 'Institute of Electrical and Electronics Engineers',
            'NEC': 'National Electrical Code',
            'IEC': 'International Electrotechnical Commission',
        }

    def _build_discipline_taxonomies(self) -> Dict[str, Set[str]]:
        """Categorized keywords mapped to technical engineering disciplines."""
        return {
            "Piping/Process": {
                "P&ID", "PFD", "PIPE", "PIPING", "VALVE", "FLANGE", "FITTING", "FLG", "EXP",
                "NPS", "DN", "SCH", "SS316L", "CS", "PSV", "PRV", "ESD", "HAZOP", "MTO",
                "NUVALOY", "AIRLINE", "FEEDER", "FLOW", "GAS", "HOPPER", "BOM", "NOZZLE"
            },
            "Mechanical/HVAC": {
                "HVAC", "DUCT", "AIR", "CFM", "AHU", "VAV", "PUMP", "COMPRESSOR", "MOTOR",
                "BEARING", "COUPLING", "FAN", "BLOWER", "COOLING", "HEATER", "EXHAUST", "DAMPER"
            },
            "Structural/Civil": {
                "STEEL", "BEAM", "COLUMN", "CONCRETE", "FOUNDATION", "HSS", "BRACKET",
                "WELD", "WELDING", "FLANGE", "GIRDER", "TRUSS", "BASEPLATE", "ANCHOR", "REBAR",
                "GRID", "FOOTING", "TOC", "BOS", "TOS", "PLATE", "GROUND BAR"
            },
            "Electrical/Instrument": {
                "PLC", "DCS", "SCADA", "VFD", "TRANSMITTER", "SENSOR", "CONDUIT", "CABLE",
                "VOLT", "AMPERE", "WATT", "CIRCUIT", "PANEL", "JB", "MCC", "WIRE", "JUNCTION",
                "INSTRUMENT", "TAG", "CONTROL", "LOOP", "I/O", "RTD", "GND", "GROUND BAR"
            },
            "General/Administrative": {
                "NOTE", "GENERAL", "SPECIFICATION", "REVISION", "REV", "DRAWING", "DWG", "BORDER",
                "APPROVED", "REVIEW", "STATUS", "INFORMATION", "DATE", "SIGNATURE", "SCALE", "TITLE"
            }
        }

    def _build_action_verbs_set(self) -> Set[str]:
        """Core engineering review action verbs."""
        return {
            "VERIFY", "UPDATE", "CONFIRM", "REMOVE", "CHECK", "ROTATE", 
            "REVISE", "ADD", "SHOW", "INDICATE", "REFERENCE", "LOCATE",
            "SPECIFY", "MATCH", "SWITCH", "CORRECT", "PROVIDE", "INCLUDE",
            "CHANGE", "DELETE", "ALIGN", "EXTEND", "CONNECT", "INSTALL",
            "CENTER", "MOVE", "FLIP", "MAKE", "KEEP", "NOTE", "HOLD"
        }

    def _build_known_typos_map(self) -> Dict[str, str]:
        """Known OCR character confusions and reviewer typos mapped to clean words."""
        return {
            'FEEDEER': 'FEEDER',
            'RECIEVER': 'RECEIVER',
            'ACUEIVERN': 'RECEIVER',
            'ACUEIVER': 'RECEIVER',
            'IOULATIUN': 'ISOLATION',
            'ISOLATIUN': 'ISOLATION',
            'OULENVID': 'SOLENOID',
            'SOLENVID': 'SOLENOID',
            'SOLENIOID': 'SOLENOID',
            'DIMENSIO': 'DIMENSION',
            'DIMENSIOS': 'DIMENSIONS',
            'DIMESION': 'DIMENSION',
            'DIMENION': 'DIMENSION',
            'FLNAGE': 'FLANGE',
            'VAVLE': 'VALVE',
            'PIPNG': 'PIPING',
            'ISOMETRC': 'ISOMETRIC',
            'SPECFICATION': 'SPECIFICATION',
            'SPECIFCATION': 'SPECIFICATION',
            'SCHEDUL': 'SCHEDULE',
            'CONECT': 'CONNECT',
            'PRESSUR': 'PRESSURE',
            'TEMPATURE': 'TEMPERATURE',
            'ELEVATON': 'ELEVATION',
            'FOUNDATON': 'FOUNDATION',
            'STRUCTUR': 'STRUCTURE',
            'ELECTIC': 'ELECTRIC',
            'TOLERENCE': 'TOLERANCE',
            'DIAMETR': 'DIAMETER',
            'THICKNES': 'THICKNESS',
            'CLEARNCE': 'CLEARANCE',
            'INSTALATION': 'INSTALLATION',
            'CORRECTON': 'CORRECTION',
            'MODIFCATION': 'MODIFICATION',
            'ALIGNMNT': 'ALIGNMENT',
            'NEST LOCATION': 'BEST LOCATION',
            'SPETTER': 'SPLITTER',
            'APROVED': 'APPROVED',
            'REQUIRS': 'REQUIRES',
            'REFERANCE': 'REFERENCE',
            'CALCULATONS': 'CALCULATIONS',
            'SPECFYING': 'SPECIFYING',
            'ARANGEMENT': 'ARRANGEMENT',
            'ARRANGEMNT': 'ARRANGEMENT',
            'LOCATON': 'LOCATION',
            'DISCRIPTION': 'DESCRIPTION',
            'CRIBTION': 'DESCRIPTION',
            'DESCRIBTION': 'DESCRIPTION',
            'CONFIM': 'CONFIRM',
            'REQURED': 'REQUIRED',
            'SECTON': 'SECTION',
            'INCLUES': 'INCLUDES',
            'EXISTIN': 'EXISTING',
            'APPROXIMAT': 'APPROXIMATE',
            'EASIER TO FOLL': 'EASIER TO FOLLOW',
            'BREAKNG': 'BREAKING',
            'MOUNTNG': 'MOUNTING',
            'DRAWNG': 'DRAWING',
            'DRAV': 'DRAWING',
            'MATERIA': 'MATERIAL',
            'REQUIRMENT': 'REQUIREMENT',
            'SCHEMATIC': 'SCHEMATIC',
            'SCHEMATICS': 'SCHEMATICS',
            'SECHEMATIC': 'SCHEMATIC',
            'SECHEMATICS': 'SCHEMATICS',
            'TEMPERA': 'TEMPERATURE',
            'TEMPERATUR': 'TEMPERATURE',
            'CONTINU': 'CONTINUE',
            'ELEVEATION': 'ELEVATION',
            'ELEVATON': 'ELEVATION',
            'HORIZONAL': 'HORIZONTAL',
            'VERTICLE': 'VERTICAL',
            'TRANSMR': 'TRANSFORMER',
            'TRANSMITER': 'TRANSMITTER',
            'EQUIPMNT': 'EQUIPMENT',
            'OPTINAL': 'OPTIONAL',
            'TYPICALY': 'TYPICALLY',
            'N.T.': 'N.T.S.',
            'NTS': 'N.T.S.',
        }

    def _build_standard_vocab(self) -> Set[str]:
        """Core engineering terms for fuzzy spell correction."""
        return {
            "FLANGE", "FLANGES", "DIMENSION", "DIMENSIONS", "VALVE", "VALVES", "PIPING", "PIPE", "PIPES",
            "ISOMETRIC", "SPECIFICATION", "SPECIFICATIONS", "SCHEDULE", "SCHEDULES", "PRESSURE", "TEMPERATURE",
            "ELEVATION", "ELEVATIONS", "FOUNDATION", "FOUNDATIONS", "STRUCTURE", "STRUCTURES", "STRUCTURAL",
            "TOLERANCE", "TOLERANCES", "CLEARANCE", "CLEARANCES", "INSTALLATION", "ALIGNMENT",
            "MATERIAL", "MATERIALS", "CALCULATION", "CALCULATIONS", "REQUIREMENT", "REQUIREMENTS",
            "ARRANGEMENT", "LOCATION", "LOCATIONS", "DESCRIPTION", "DESCRIPTIONS", "EXISTING", "APPROXIMATE",
            "DRAWING", "DRAWINGS", "SECTION", "SECTIONS", "RECEIVER", "FEEDER", "SPLITTER", "APPROVED",
            "VERIFY", "UPDATE", "CONFIRM", "REMOVE", "CHECK", "ROTATE", "REVISE",
            "CORRECTION", "CORRECTIONS", "MODIFICATION", "MODIFICATIONS",
            "EQUIPMENT", "INSTRUMENT", "INSTRUMENTS", "TRANSMITTER", "TRANSMITTERS"
        }

    def _build_action_verbs_set(self) -> Set[str]:
        """Core engineering review action verbs."""
        return {
            "VERIFY", "UPDATE", "CONFIRM", "REMOVE", "CHECK", "ROTATE", 
            "REVISE", "ADD", "SHOW", "INDICATE", "REFERENCE", "LOCATE",
            "SPECIFY", "MATCH", "SWITCH", "CORRECT", "PROVIDE", "INCLUDE",
            "CHANGE", "DELETE", "ALIGN", "EXTEND", "CONNECT", "INSTALL"
        }

    def _build_comprehensive_vocabulary(self) -> Set[str]:
        """
        Comprehensive multi-discipline engineering vocabulary + standard English review words.
        Used for sub-millisecond, domain-safe spell checking and verification.
        """
        vocab = {
            # Grammar, Prepositions, Conjunctions & Common Words
            "A", "AN", "THE", "AND", "OR", "NOR", "BUT", "FOR", "IF", "OF", "AT", "BY", 
            "TO", "IN", "ON", "OFF", "OUT", "UP", "DOWN", "OVER", "UNDER", "ABOVE", "BELOW",
            "FROM", "INTO", "WITH", "WITHOUT", "THROUGH", "BETWEEN", "AMONG", "DURING",
            "BEFORE", "AFTER", "SINCE", "UNTIL", "AGAINST", "ABOUT", "ACROSS", "ALONG",
            "BEHIND", "BEYOND", "INSIDE", "OUTSIDE", "NEAR", "BESIDE", "TOWARD", "TOWARDS",
            "THIS", "THAT", "THESE", "THOSE", "THERE", "HERE", "WHERE", "WHEN", "WHICH",
            "WHAT", "WHO", "WHOM", "WHOSE", "WHY", "HOW", "ALL", "ANY", "EACH", "EVERY",
            "BOTH", "EITHER", "NEITHER", "SOME", "NONE", "ONE", "TWO", "THREE", "FOUR",
            "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN", "FIRST", "SECOND", "THIRD",
            "IS", "AM", "ARE", "WAS", "WERE", "BE", "BEEN", "BEING", "HAVE", "HAS", "HAD",
            "HAVING", "DO", "DOES", "DID", "DONE", "DOING", "WILL", "WOULD", "SHALL", "SHOULD",
            "CAN", "COULD", "MAY", "MIGHT", "MUST", "OUGHT", "NEED", "NEEDS", "NEEDED", "NEEDING",
            "WANT", "WANTS", "WANTED", "WANTING", "BILL", "BILLS", "LASER", "LASERS",
            "SCAN", "SCANS", "SCANNED", "SCANNING", "DATE", "DATES", "DATED", "DATING",
            "QUANTITY", "QUANTITIES", "TOTAL", "TOTALS", "AMOUNT", "AMOUNTS", "COUNT", "COUNTS",
            "AS", "SO", "THAN", "THEN", "TOO", "VERY", "MUCH", "MORE", "MOST", "LESS", "LEAST",
            "FEW", "MANY", "SEVERAL", "ENOUGH", "WELL", "GOOD", "BETTER", "BEST", "POOR",
            "BAD", "WORSE", "WORST", "GREAT", "GREATER", "GREATEST", "SAME", "OTHER", "ANOTHER",
            "SUCH", "LIKE", "EVEN", "JUST", "ALSO", "ONLY", "ALREADY", "STILL", "YET", "NOW",
            "PLEASE", "THANKS", "THANK", "YOU", "YOUR", "YOURS", "OUR", "OURS", "THEIR", "THEIRS",
            "HIS", "HER", "HERS", "ITS", "MY", "MINE", "WHOLE", "PART", "PARTS", "HALF",

            # Review Actions & Directives
            "VERIFY", "VERIFIES", "VERIFIED", "VERIFYING", "VERIFICATION",
            "UPDATE", "UPDATES", "UPDATED", "UPDATING",
            "CONFIRM", "CONFIRMS", "CONFIRMED", "CONFIRMING", "CONFIRMATION",
            "REMOVE", "REMOVES", "REMOVED", "REMOVING", "REMOVAL",
            "CHECK", "CHECKS", "CHECKED", "CHECKING",
            "ROTATE", "ROTATES", "ROTATED", "ROTATING", "ROTATION",
            "REVISE", "REVISES", "REVISED", "REVISING", "REVISION", "REVISIONS",
            "ADD", "ADDS", "ADDED", "ADDING", "ADDITION", "ADDITIONS",
            "SHOW", "SHOWS", "SHOWN", "SHOWING",
            "INDICATE", "INDICATES", "INDICATED", "INDICATING", "INDICATION",
            "REFERENCE", "REFERENCES", "REFERENCED", "REFERENCING",
            "LOCATE", "LOCATES", "LOCATED", "LOCATING", "LOCATION", "LOCATIONS",
            "SPECIFY", "SPECIFIES", "SPECIFIED", "SPECIFYING", "SPECIFICATION", "SPECIFICATIONS",
            "MATCH", "MATCHES", "MATCHED", "MATCHING",
            "SWITCH", "SWITCHES", "SWITCHED", "SWITCHING",
            "CORRECT", "CORRECTS", "CORRECTED", "CORRECTING", "CORRECTION", "CORRECTIONS",
            "PROVIDE", "PROVIDES", "PROVIDED", "PROVIDING",
            "INCLUDE", "INCLUDES", "INCLUDED", "INCLUDING", "INCLUSION",
            "CHANGE", "CHANGES", "CHANGED", "CHANGING",
            "DELETE", "DELETES", "DELETED", "DELETING", "DELETION",
            "ALIGN", "ALIGNS", "ALIGNED", "ALIGNING", "ALIGNMENT",
            "EXTEND", "EXTENDS", "EXTENDED", "EXTENDING", "EXTENSION",
            "CONNECT", "CONNECTS", "CONNECTED", "CONNECTING", "CONNECTION", "CONNECTIONS",
            "INSTALL", "INSTALLS", "INSTALLED", "INSTALLING", "INSTALLATION", "INSTALLATIONS",
            "CENTER", "CENTERS", "CENTERED", "CENTERING",
            "MOVE", "MOVES", "MOVED", "MOVING", "MOVEMENT",
            "FLIP", "FLIPS", "FLIPPED", "FLIPPING",
            "MAKE", "MAKES", "MADE", "MAKING",
            "KEEP", "KEEPS", "KEPT", "KEEPING", "MIND",
            "NOTE", "NOTES", "NOTED", "NOTING",
            "HOLD", "HOLDS", "HELD", "HOLDING",
            "STOP", "STOPS", "STOPPED", "STOPPING",
            "FAIL", "FAILS", "FAILED", "FAILING", "FAILURE",
            "REJECT", "REJECTS", "REJECTED", "REJECTING", "REJECTION",
            "APPROVE", "APPROVES", "APPROVED", "APPROVING", "APPROVAL",
            "REVIEW", "REVIEWS", "REVIEWED", "REVIEWING", "REVIEWER", "REVIEWERS",
            "MARK", "MARKS", "MARKED", "MARKING", "MARKUP", "MARKUPS",
            "SEE", "SEEN", "REFER", "REFERS", "REFERRED", "REFERRING", "CONSULT",

            # Engineering Disciplines & Concepts
            "GENERAL", "GENERATOR", "GENERATORS", "GENERATE", "GENERATED", "GENERATING",
            "MAIN", "PRIMARY", "SECONDARY", "AUXILIARY", "INTERMEDIATE", "SERVICE", "SERVICES",
            "SYSTEM", "SYSTEMS", "EQUIPMENT", "FACILITY", "FACILITIES", "PLANT", "PLANTS",
            "PROJECT", "PROJECTS", "CONTRACT", "CONTRACTS", "VENDOR", "VENDORS", "CLIENT", "CLIENTS",
            "ENGINEER", "ENGINEERS", "ENGINEERING", "DESIGN", "DESIGNS", "DESIGNER", "DESIGNERS",
            "DESIGNED", "DESIGNING", "LEGEND", "LEGENDS", "TABLE", "TABLES", "LIST", "LISTS",
            "ELECTRICAL", "MECHANICAL", "STRUCTURAL", "CIVIL", "PIPING", "PROCESS", "PROCESSES",
            "PROCESSED", "PROCESSING", "PROCEED", "PROCEEDS", "PROCEEDED", "PROCEEDING",
            "RATING", "RATINGS", "RATED", "RATE", "RATES", "CENTERLINE", "CENTERLINES",
            "COORDINATION", "COORDINATE", "COORDINATES", "COORDINATED", "COORDINATING",
            "FABRICATION", "FABRICATE", "FABRICATED", "FABRICATING", "ERECTION", "CONSTRUCTION",
            "INSPECTION", "INSPECT", "INSPECTED", "INSPECTING", "MAINTENANCE", "MAINTAIN",
            "OPERATION", "OPERATIONS", "OPERATE", "OPERATED", "OPERATING", "OPERATOR", "OPERATORS",
            "SAFETY", "SAFE", "SAFELY", "QUALITY", "QUALIFIED", "TEST", "TESTS", "TESTED", "TESTING",
            "PACKAGE", "PACKAGES", "PACKAGED", "SUPPLIER", "SUPPLIERS", "SUPPLY", "SUPPLIES",
            "INSTRUMENTATION", "CONTROL", "CONTROLS", "AUTOMATION", "COMMUNICATION",
            "SCHEMATIC", "SCHEMATICS", "DIAGRAM", "DIAGRAMS", "DRAWING", "DRAWINGS",
            "LAYOUT", "LAYOUTS", "ISOMETRIC", "ISOMETRICS", "ELEVATION", "ELEVATIONS",
            "SECTION", "SECTIONS", "DETAIL", "DETAILS", "PLAN", "PLANS", "PROFILE", "PROFILES",
            "AS-BUILT", "REQUIREMENT", "REQUIREMENTS", "TOLERANCE", "TOLERANCES",
            "DIMENSION", "DIMENSIONS", "CLEARANCE", "CLEARANCES", "SPACING", "SPACINGS",
            "SCHEDULE", "SCHEDULES", "SPREADSHEET", "SPREADSHEETS", "PUNCHLIST",

            # Electrical & Controls
            "RECEIVER", "RECEIVERS", "FEEDER", "FEEDERS", "TRANSMITTER", "TRANSMITTERS",
            "SOLENOID", "SOLENOIDS", "ISOLATION", "VALVE", "VALVES", "TERMINAL", "TERMINALS",
            "BLOCK", "BLOCKS", "ARRANGEMENT", "ARRANGEMENTS", "CIRCUIT", "CIRCUITS",
            "BREAKER", "BREAKERS", "TRANSFORMER", "TRANSFORMERS", "MOTOR", "MOTORS",
            "PUMP", "PUMPS", "COMPRESSOR", "COMPRESSORS", "CONDUIT", "CONDUITS",
            "CABLE", "CABLES", "VOLT", "VOLTS", "VOLTAGE", "VOLTAGES", "AMPERE", "AMPS",
            "CURRENT", "CURRENTS", "WATT", "WATTS", "POWER", "GROUND", "GROUNDING",
            "BAR", "BARS", "BUSBAR", "BUSBARS", "PANEL", "PANELS", "ENCLOSURE", "ENCLOSURES",
            "JUNCTION", "JUNCTIONS", "BOX", "BOXES", "RELAY", "RELAYS", "FUSE", "FUSES",
            "SWITCH", "SWITCHES", "SENSOR", "SENSORS", "TRANSDUCER", "TRANSDUCERS",
            "ETHERNET", "PANDUIT", "CONNECTOR", "CONNECTORS", "LUG", "LUGS", "WIRE", "WIRES",
            "WIRING", "TRAIN", "TRAINS", "ECOPOD", "HMI", "PLC", "DCS", "VFD", "SCADA",
            "UPS", "RTD", "SIGNAL", "SIGNALS", "DIGITAL", "ANALOG", "INPUT", "INPUTS",
            "OUTPUT", "OUTPUTS", "LOOP", "LOOPS", "TAG", "TAGS", "CUTOUT", "CUTOUTS",
            "OPERATOR", "INDUSTRIAL", "MOUNTING", "LABEL", "LABELS", "POCKET", "DATA",
            "NAMEPLATE", "NAMEPLATES", "REFLECTED", "INSTEAD", "PARTICULARLY", "CREATED",

            # Mechanical & Piping
            "FLANGE", "FLANGES", "GASKET", "GASKETS", "FITTING", "FITTINGS", "ELBOW", "ELBOWS",
            "TEE", "TEES", "REDUCER", "REDUCERS", "UNION", "UNIONS", "COUPLING", "COUPLINGS",
            "NOZZLE", "NOZZLES", "PIPE", "PIPES", "TUBING", "HOSE", "HOSES", "DUCT", "DUCTS",
            "DAMPER", "DAMPERS", "BEARING", "BEARINGS", "SEAL", "SEALS", "PRESSURE", "PRESSURES",
            "TEMPERATURE", "TEMPERATURES", "DIFFERENTIAL", "FLOW", "FLOWS", "LEVEL", "LEVELS",
            "EXPANSION", "EXPANSIONS", "HEATER", "HEATERS", "COOLER", "COOLERS", "COOLING",
            "AIR", "WATER", "GAS", "GASES", "OIL", "OILS", "STEAM", "DRAIN", "DRAINS",
            "VENT", "VENTS", "BLEED", "SUCTION", "DISCHARGE", "BYPASS", "HEADER", "HEADERS",
            "MANIFOLD", "MANIFOLDS", "MATERIAL", "MATERIALS",

            # Structural & Civil
            "STEEL", "CONCRETE", "FOUNDATION", "FOUNDATIONS", "FOOTING", "FOOTINGS",
            "COLUMN", "COLUMNS", "BEAM", "BEAMS", "GIRDER", "GIRDERS", "TRUSS", "TRUSSES",
            "BRACKET", "BRACKETS", "BASEPLATE", "BASEPLATES", "ANCHOR", "ANCHORS",
            "BOLT", "BOLTS", "NUT", "NUTS", "SCREW", "SCREWS", "WASHER", "WASHERS",
            "WELD", "WELDS", "WELDING", "REBAR", "PLATE", "PLATES", "CHANNEL", "CHANNELS",
            "ANGLE", "ANGLES", "FRAME", "FRAMES", "FRAMING", "SUPPORT", "SUPPORTS",
            "HANGER", "HANGERS", "SLAB", "SLABS", "WALL", "WALLS", "ROOF", "FLOOR", "FLOORS",

            # Physical Properties, Units & Visual Attributes
            "SOLID", "DASHED", "DOTTED", "THICKNESS", "SIZE", "SIZES", "COLOR", "COLORS", "COLORED",
            "BLACK", "WHITE", "RED", "BLUE", "GREEN", "YELLOW", "ORANGE", "PURPLE", "BROWN", "GRAY", "GREY",
            "LONG", "LONGER", "LONGEST", "SHORT", "SHORTER", "SHORTEST",
            "HIGH", "HIGHER", "HIGHEST", "LOW", "LOWER", "LOWEST",
            "LARGE", "LARGER", "LARGEST", "SMALL", "SMALLER", "SMALLEST",
            "WIDE", "WIDER", "WIDEST", "NARROW", "NARROWER", "NARROWEST",
            "THICK", "THICKER", "THICKEST", "THIN", "THINNER", "THINNEST",
            "DEEP", "DEEPER", "DEEPEST", "SHALLOW", "SHALLOWER", "SHALLOWEST",
            "HEAVY", "HEAVIER", "HEAVIEST", "LIGHT", "LIGHTER", "LIGHTEST",
            "TIGHT", "TIGHTER", "TIGHTEST", "LOOSE", "LOOSER", "LOOSEST",
            "HOT", "HOTTER", "HOTTEST", "COLD", "COLDER", "COLDEST",
            "WARM", "WARMER", "WARMEST", "COOL", "COOLER", "COOLEST",
            "CLEAN", "CLEANER", "CLEANEST", "DIRTY", "DIRTIER", "DIRTIEST",
            "HARD", "HARDER", "HARDEST", "SOFT", "SOFTER", "SOFTEST",
            "EARLY", "EARLIER", "EARLIEST", "LATE", "LATER", "LATEST",
            "NEAR", "NEARER", "NEAREST", "FAR", "FARTHER", "FARTHEST",
            "FAST", "FASTER", "FASTEST", "SLOW", "SLOWER", "SLOWEST",
            "GREAT", "GREATER", "GREATEST", "BETTER", "BEST", "WORSE", "WORST",
            "ARROW", "ARROWS", "LINE", "LINES", "SHAPE", "SHAPES", "CIRCLE", "CIRCLES",
            "RECTANGLE", "RECTANGLES", "SYMBOL", "SYMBOLS", "TEXT", "FONT", "FONTS",
            "SPACE", "SPACES", "GAP", "GAPS", "CLEAR", "INCORRECT", "WRONG",
            "RIGHT", "LEFT", "TOP", "BOTTOM", "UPPER", "LOWER", "FRONT", "BACK",
            "SIDE", "SIDES", "REAR", "CENTER", "INSIDE", "OUTSIDE", "NORMAL",
            "CUSTOM", "SPECIAL", "EXISTING", "PROPOSED", "FUTURE", "NEW", "OLD",
            "CURRENT", "PREVIOUS", "SIMILAR", "EQUAL", "EQUIVALENT", "APPROXIMATE", "EXACT",
            "FINAL", "PARTIAL", "COMPLETE", "COMPLETED", "INCOMPLETE",
            "OPTIONAL", "TYPICAL", "STANDARD", "STANDARDS",
            "FEET", "METER", "METERS", "INCH", "INCHES", "DIAMETER", "RADIUS", "BORDER",
            "P&ID", "BOM", "NPS", "SCH", "HSS", "PLC", "DCS", "VFD", "SCADA", "GND",
            "N.T.S.", "TYP.", "REF.", "DWG", "REV", "QTY", "NO.", "MAX", "MIN", "STAMP",
            "AX", "ERP", "SAP", "CAD", "PDF", "DXF", "XLS", "CSV", "USE", "USES", "USED", "USING",
        }
        return vocab

    # =========================================================================
    # 2. CORE TEXT CLEANING PIPELINE
    # =========================================================================

    def clean_text(self, raw_text: str) -> CleanedCommentDTO:
        """
        Clean, normalize, correct, and enrich a single reviewer comment string.
        """
        if not raw_text:
            return CleanedCommentDTO(
                original_text="",
                cleaned_text="",
                corrections=[],
                similarity_score=1.0,
                sub_actions=[],
                reviewer_initials=None,
                action_verb=None,
                priority_level="MEDIUM",
                engineering_terms_found=[],
                is_duplicate_of=None
            )

        corrections: List[CorrectionDTO] = []
        text = raw_text

        # Step 1: Strip OCR Noise, Stray Artifacts & Unicode Replacement Characters
        text, noise_corrections = self._strip_ocr_noise(text)
        corrections.extend(noise_corrections)

        # Step 2: Extract Reviewer Initials & Sign-offs before word-level modifications
        reviewer_initials, text_after_init = self._extract_reviewer_initials(text)

        # Step 3: Domain-Safe Spell Correction & OCR Substitution Correction
        text, typo_corrections = self._apply_domain_spell_correction(text)
        corrections.extend(typo_corrections)

        # Step 4: Expand Engineering Abbreviations (only if explicitly enabled)
        if self.expand_acronyms:
            text, abbr_corrections = self._expand_abbreviations(text)
            corrections.extend(abbr_corrections)

        # Step 5: Normalize Whitespace & Punctuation
        text, ws_corrections = self._normalize_whitespace(text)
        corrections.extend(ws_corrections)

        # Step 6: Identify Multi-Action Sub-Clauses
        sub_actions = self._segment_actions(text)

        # Step 7: Detect Action Verbs & Priority Level
        action_verb = self._detect_action_verb(text)
        priority_level = self._detect_priority(text)
        engineering_terms = self._detect_engineering_terms(raw_text)

        similarity = difflib.SequenceMatcher(None, raw_text, text).ratio()

        return CleanedCommentDTO(
            original_text=raw_text,
            cleaned_text=text,
            corrections=corrections,
            similarity_score=round(similarity, 3),
            sub_actions=sub_actions,
            reviewer_initials=reviewer_initials,
            action_verb=action_verb,
            priority_level=priority_level,
            engineering_terms_found=engineering_terms,
            is_duplicate_of=None
        )

    # =========================================================================
    # 3. HELPER CLEANING & SPELL CHECKING STAGES
    # =========================================================================

    def _strip_ocr_noise(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Removes scan artifacts while preserving technical tags, dimensions, and fractions."""
        corrections = []
        original = text

        # Replace Unicode replacement characters and encoding glitches
        text = text.replace('\ufffd', ' ').replace('\u00a0', ' ')
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        # Remove OCR artifact tokens like "f=", "_~", "HL" on own line, stray pipes
        text = re.sub(r'(?:^|\s)f\s*=\s*', ' ', text)
        text = text.replace('_~', ' ')
        
        # Remove standalone vertical pipes and backslash noise e.g. " | ", " \ ", " \\ "
        text = re.sub(r'(?:^|\s)[\\/|;~]+\s*(?=[A-Za-z0-9])', ' ', text)
        text = re.sub(r'\s+[\\/|;~]+(?:\s|$)', ' ', text)

        # Strip repeated non-alphanumeric noise symbols (e.g. !!!! -> !, ??? -> ?, ///// -> /)
        noise_pattern = re.compile(r'([!@#$%\^&*()_+={}\[\]:;"\'<>,.?/\\|`~])\1+')
        if noise_pattern.search(text):
            text = noise_pattern.sub(r'\1', text)

        # Remove stray leading noise symbols
        text = re.sub(r'^[\\/|:;\s~_]+', '', text)
        
        # Clean double spaces
        text = re.sub(r'\s+', ' ', text).strip()

        if text != original:
            corrections.append(CorrectionDTO(original=original, corrected=text, correction_type='noise_removal'))

        return text, corrections

    def _normalize_whitespace(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Normalizes spaces around parentheses, hyphens, and quotes."""
        corrections = []
        original = text

        # Standardize multiple spaces and newlines
        text = re.sub(r'[\r\n\t]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()

        # Fix spacing around parentheses: "( text )" -> "(text)"
        text = re.sub(r'\(\s+', '(', text)
        text = re.sub(r'\s+\)', ')', text)

        # Fix spaced single quotes/backticks in dimensions: 345 \' - 11 -> 345'-11
        text = re.sub(r"(\d+)\s+'\s*-\s*(\d+)", r"\1'-\2", text)

        if text != original:
            corrections.append(CorrectionDTO(original=original, corrected=text, correction_type='whitespace'))

        return text, corrections

    def _is_technical_token(self, token: str) -> bool:
        """
        Returns True if token is an equipment tag, part code, model ID,
        dimension with fraction, wire label, or reference that must NOT be spell-checked.
        Examples: 'XV-001', 'Z-ISTPHCH1MTL', '5-3552-11', '24VDC', '120VAC', '14GA',
                  '345'-11', '3/4"', 'SS316L', 'SCH40', 'N.T.S.', 'SK-409072'
        """
        clean = token.strip('.,!?;:()"\'')
        if not clean:
            return True

        # Pure numbers or numbers with units / fractions: 12, 14GA, 24VDC, 60mm, 3/4", 8"
        if re.match(r'^\d+(?:/\d+)?(?:"|\'|mm|cm|in|ft|m|GA|VDC|VAC|V|A|W|Hz|#|k|HP)?$', clean, re.IGNORECASE):
            return True

        # Dimension notations: 345'-11, 8"-SCH40, 1/2"
        if re.match(r'^\d+[\'-]\d+(?:/\d+)?"?$', clean):
            return True

        # Tag/Model patterns with hyphens or underscores: XV-001, Z-ISTPHCH1MTL, 5-3552-11, C-54718-31-002
        if re.match(r'^[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+$', clean):
            return True

        # Alphanumeric codes with numbers mixed in: SS316L, 14GA, 24VDC, STB1, HMI1, A02, B01
        if any(c.isdigit() for c in clean) and any(c.isalpha() for c in clean):
            return True

        # Standard abbreviations with dots: N.T.S., TYP., REF., DWG.
        if '.' in clean:
            return True

        # Short tokens of length <= 2 that are capital acronyms or single characters
        if len(clean) <= 2:
            return True

        return False

    def _is_valid_word(self, word: str) -> bool:
        """Check if word or its basic morphological variants exist in vocabulary."""
        upper = word.upper()
        if upper in self.vocab_lookup:
            return True
        # Check plural / verb inflections
        if upper.endswith('S') and upper[:-1] in self.vocab_lookup:
            return True
        if upper.endswith('ES') and upper[:-2] in self.vocab_lookup:
            return True
        if upper.endswith('ED') and (upper[:-2] in self.vocab_lookup or upper[:-1] in self.vocab_lookup):
            return True
        if upper.endswith('ING') and (upper[:-3] in self.vocab_lookup or upper[:-3] + 'E' in self.vocab_lookup):
            return True
        if upper.endswith('LY') and upper[:-2] in self.vocab_lookup:
            return True
        return False

    def _correct_word_spelling(self, token: str) -> str:
        """
        Corrects a single word token using engineering & English vocabulary with OCR confusion costs.
        Preserves original casing and punctuation.
        """
        # Separate leading/trailing punctuation
        prefix_match = re.match(r'^([^A-Za-z0-9]+)', token)
        suffix_match = re.search(r'([^A-Za-z0-9]+)$', token)
        prefix = prefix_match.group(1) if prefix_match else ""
        suffix = suffix_match.group(1) if suffix_match else ""

        core = token[len(prefix):len(token) - len(suffix) if suffix else len(token)]
        if not core:
            return token

        # If it's a technical part number, dimension, tag, or formula -> keep as-is
        if self._is_technical_token(core):
            return token

        upper_core = core.upper()

        # Check known typo map first
        if upper_core in self.known_typos:
            corrected = self.known_typos[upper_core]
            return prefix + self._match_casing(core, corrected) + suffix

        # Check if already in valid vocabulary or valid morphological form
        if self._is_valid_word(upper_core):
            return token

        # For short words (length <= 3), never fuzzy-match to avoid false positives (e.g. OF, FOR, AND)
        if len(core) <= 3:
            return token

        # Candidate search using Levenshtein distance with length filter
        best_match = None
        min_dist = float('inf')
        core_len = len(upper_core)

        for candidate in self.vocabulary:
            cand_len = len(candidate)
            if abs(cand_len - core_len) > 2:
                continue

            # Compute Levenshtein distance
            dist = textdistance.levenshtein.distance(upper_core, candidate)
            
            if dist <= 2:
                # Bonus if first letter matches
                if upper_core[0] == candidate[0]:
                    dist -= 0.3
                
                # Check maximum allowed distance based on word length
                max_allowed = 1.0 if core_len <= 5 else 2.0
                if dist < min_dist and dist <= max_allowed:
                    min_dist = dist
                    best_match = candidate

        if best_match and min_dist < float('inf'):
            return prefix + self._match_casing(core, best_match) + suffix

        return token

    def _match_casing(self, original: str, replacement: str) -> str:
        """Applies original word casing (UPPER, Title, or lower) to replacement."""
        if original.isupper():
            return replacement.upper()
        if original.istitle():
            return replacement.capitalize()
        if original.islower():
            return replacement.lower()
        return replacement

    def _apply_domain_spell_correction(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Applies domain-safe spelling and phrase corrections."""
        corrections = []
        original = text

        # 1. Multi-word phrase corrections first
        phrase_fixes = [
            (r'\bNEST LOCATION\b', 'BEST LOCATION'),
            (r'\bEASIER TO FOLL\b', 'EASIER TO FOLLOW'),
            (r'\bBILL OF MATERIA\b', 'BILL OF MATERIALS'),
            (r'\bGENERAL NO\b', 'GENERAL NOTES'),
            (r'\bDIMENSIONS OF EXISTIN\b', 'DIMENSIONS OF EXISTING'),
            (r'\bCL EL\b', 'CENTERLINE ELEVATION'),
            (r'\bCHANGE TO 60MM\b', 'CHANGE TO 60mm'),
            (r'\bDRAV ING\b', 'DRAWING'),
            (r'\bDRAV\b', 'DRAWING'),
            (r'\bAIN ACUEIVERN\b', 'AIR RECEIVER'),
            (r'\bAIN ACUEIVER\b', 'AIR RECEIVER'),
            (r'\bIOULATIUN VALVE\b', 'ISOLATION VALVE'),
            (r'\bOULENVID\b', 'SOLENOID'),
            (r'\bSOLENVID\b', 'SOLENOID'),
            (r'\bOPTIONAL \(TYPICAL\)\b', 'OPTIONAL (TYPICAL)'),
            (r'\bTERMINAL  BLOCK\b', 'TERMINAL BLOCK'),
        ]
        for pattern, replacement in phrase_fixes:
            if re.search(pattern, text, re.IGNORECASE):
                new_text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
                if new_text != text:
                    corrections.append(CorrectionDTO(original=text, corrected=new_text, correction_type='spelling'))
                    text = new_text

        # 2. Token-level domain-safe spell checking
        words = text.split()
        cleaned_words = []
        for w in words:
            corrected_w = self._correct_word_spelling(w)
            if corrected_w != w:
                corrections.append(CorrectionDTO(original=w, corrected=corrected_w, correction_type='spelling'))
            cleaned_words.append(corrected_w)

        text = ' '.join(cleaned_words)
        return text, corrections

    def _expand_abbreviations(self, text: str) -> Tuple[str, List[CorrectionDTO]]:
        """Expands unambiguous engineering acronyms into full standard terminology."""
        corrections = []
        original = text

        words = text.split()
        expanded_words = []
        for word in words:
            clean_word = word.strip('.,!?;:()"\'')
            if clean_word in self.engineering_dict:
                expanded = self.engineering_dict[clean_word]
                expanded_words.append(word.replace(clean_word, expanded))
                corrections.append(CorrectionDTO(original=clean_word, corrected=expanded, correction_type='abbreviation'))
            else:
                expanded_words.append(word)

        text = ' '.join(expanded_words)
        return text, corrections

    def _extract_reviewer_initials(self, text: str) -> Tuple[Optional[str], str]:
        """Extracts reviewer attribution like '-JDM', '-JCM', '-BEK', '-MWR', '-JJD', 'By: BreKol'."""
        initials = None
        
        # Pattern 1: Suffix initials like "-JDM", "-JCM", "-BEK", "-JJD", "-MWR"
        suffix_match = re.search(r'(?:^|\s)[-–—]\s*([A-Z]{2,4})(?:\s*|\.?)$', text)
        if suffix_match:
            initials = suffix_match.group(1).upper()
            return initials, text

        # Pattern 2: Suffix without hyphen e.g. "BELONGS JCM" or "TYPICAL FOR ALL JCM"
        trailing_match = re.search(r'\b([A-Z]{2,3})$', text.strip())
        if trailing_match and trailing_match.group(1) in {"JCM", "JDM", "MWR", "BEK", "JJD", "UCC", "UCCI"}:
            initials = trailing_match.group(1)
            return initials, text

        # Pattern 3: Explicit signature "By: BreKol" or "BY DATE BreKol"
        by_match = re.search(r'(?:BY|By|BY DATE|By:)\s+([A-Za-z0-9_-]+)', text)
        if by_match:
            initials = by_match.group(1)
            return initials, text

        return None, text


    def _segment_actions(self, text: str) -> List[str]:
        """Detects multi-action punch list items (e.g. '1. ... 2. ... 3. ...' or '(A) ... (B) ...')."""
        numbered_pattern = re.split(r'(?:\d+[\.\)]|\([A-Za-z\d]+\))\s+', text)
        if len(numbered_pattern) > 1:
            actions = [act.strip() for act in numbered_pattern if len(act.strip()) > 3]
            if len(actions) > 1:
                return actions

        clause_pattern = re.split(r';|\b(?:ALSO VERIFY|AND REVISE|PLEASE ALSO)\b', text, flags=re.IGNORECASE)
        if len(clause_pattern) > 1:
            actions = [act.strip() for act in clause_pattern if len(act.strip()) > 5]
            if len(actions) > 1:
                return actions

        return [text] if text else []

    def _detect_action_verb(self, text: str) -> Optional[str]:
        """Finds primary action verb in comment."""
        upper_text = text.upper()
        words = re.findall(r'\b[A-Z]+\b', upper_text)
        for w in words:
            if w in self.action_verbs:
                return w
        return None

    def _detect_priority(self, text: str) -> str:
        """Determines action priority level based on sentiment and urgency."""
        upper = text.upper()
        for kw in self.high_priority_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', upper):
                return "HIGH"
        for kw in self.medium_priority_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', upper):
                return "MEDIUM"
        for kw in self.low_priority_keywords:
            if re.search(r'\b' + re.escape(kw) + r'\b', upper):
                return "LOW"
        return "MEDIUM"

    def _detect_engineering_terms(self, text: str) -> List[str]:
        """Extracts all domain terms present in text."""
        upper = text.upper()
        found = []
        for term in self.engineering_dict.keys():
            if re.search(r'\b' + re.escape(term) + r'\b', upper):
                found.append(term)
        return found

    # =========================================================================
    # 4. BATCH CLEANING & SEMANTIC DUPLICATE DETECTION
    # =========================================================================

    def clean_batch(self, comments: List[Dict[str, Any]], drawing_id: str = '') -> TextCleaningResultDTO:
        """Processes a list of raw comments and performs duplicate detection."""
        start_time = time.time()
        cleaned = []
        texts = []

        for comment in comments:
            raw = comment.get('text', '') or comment.get('raw_text', '')
            res = self.clean_text(raw)
            cleaned.append(res)
            texts.append(res.cleaned_text)

        dups = self.detect_duplicates(texts)

        for orig_idx, dup_idx in dups:
            if dup_idx < len(cleaned):
                cleaned[dup_idx].is_duplicate_of = f"CMT-{orig_idx}"

        elapsed = (time.time() - start_time) * 1000
        return TextCleaningResultDTO(
            drawing_id=drawing_id,
            total_comments=len(comments),
            cleaned_comments=cleaned,
            duplicates_removed=len(dups),
            processing_time_ms=elapsed
        )

    def detect_duplicates(self, texts: List[str], threshold: float = 0.85) -> List[Tuple[int, int]]:
        """
        Detects duplicate or highly similar comments using SequenceMatcher.
        Returns list of (canonical_index, duplicate_index).
        """
        duplicates = []
        for i in range(len(texts)):
            if not texts[i].strip():
                continue
            for j in range(i + 1, len(texts)):
                if not texts[j].strip():
                    continue
                ratio = difflib.SequenceMatcher(None, texts[i].upper(), texts[j].upper()).ratio()
                if ratio >= threshold:
                    duplicates.append((i, j))
        return duplicates

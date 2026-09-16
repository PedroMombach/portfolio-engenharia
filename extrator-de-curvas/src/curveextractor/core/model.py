"""Geometry is immutable; capture replaces tuples until a curve is locked."""

from dataclasses import dataclass, field, replace
from uuid import uuid4

from .errors import DomainError


def new_id() -> str:
    return uuid4().hex


@dataclass(frozen=True)
class AxisPoint:
    px: float
    py: float
    vx: float
    vy: float


@dataclass(frozen=True)
class CoordinateSystem:
    points: tuple[AxisPoint, ...] = ()
    x_scale: str = "lin"
    y_scale: str = "lin"
    id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        object.__setattr__(self, "points", tuple(self.points))

    def duplicate(self) -> "CoordinateSystem":
        return replace(self, id=new_id(), points=tuple(replace(p) for p in self.points))


@dataclass(frozen=True)
class Style:
    color: str = "#0072B2"
    marker: str = "circle"
    width: float = 2.0


@dataclass(frozen=True)
class Source:
    document_id: str
    page_index: int


@dataclass
class Curve:
    name: str
    source: Source
    coordinate_system: CoordinateSystem = field(default_factory=CoordinateSystem)
    points_px: tuple[tuple[float, float], ...] = ()
    style: Style = field(default_factory=Style)
    id: str = field(default_factory=new_id)
    locked: bool = False

    def __post_init__(self) -> None:
        # Every curve owns a calibration even when constructed from another curve.
        object.__setattr__(self, "coordinate_system", self.coordinate_system.duplicate())
        object.__setattr__(self, "points_px", tuple(tuple(p) for p in self.points_px))

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "locked", False) and name in {
            "points_px",
            "coordinate_system",
            "source",
            "locked",
        }:
            raise DomainError("locked")
        if name == "points_px":
            value = tuple(tuple(p) for p in value)
        if name == "coordinate_system":
            value = replace(value, points=tuple(replace(p) for p in value.points))
        super().__setattr__(name, value)

    def add_point(self, x: float, y: float) -> None:
        self.points_px = (*self.points_px, (float(x), float(y)))

    def lock(self) -> None:
        from .transform import Transform

        Transform(self.coordinate_system)
        if not self.points_px:
            raise DomainError("empty_curve")
        self.locked = True


@dataclass(frozen=True)
class PageImage:
    document_id: str
    page_index: int
    width_px: int
    height_px: int
    raster_dpi: int
    png_bytes: bytes


@dataclass
class Document:
    origin_path: str | None
    sha256: str
    kind: str
    pages: list[PageImage] = field(default_factory=list)
    id: str = field(default_factory=new_id)
    page_count: int = 1


@dataclass
class Project:
    documents: list[Document] = field(default_factory=list)
    curves: list[Curve] = field(default_factory=list)
    main_curve_id: str | None = None
    app_version: str = "1.0.0"
    next_curve_number: int = 1

    def new_curve(self, source: Source, name: str) -> Curve:
        curve = Curve(name=name, source=source)
        self.next_curve_number += 1
        self.curves.append(curve)
        return curve

    def page(self, source: Source) -> PageImage:
        for document in self.documents:
            if document.id == source.document_id:
                for page in document.pages:
                    if page.page_index == source.page_index:
                        return page
        raise DomainError("missing_page")

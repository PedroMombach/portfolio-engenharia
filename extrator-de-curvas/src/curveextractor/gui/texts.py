"""All user-facing Portuguese strings."""


class T:
    OVERWRITE = "Os seguintes arquivos já existem. Substituí-los?\n{files}"
    DESTINATION_INVALID = "Escolha um nome e caminho válidos para a exportação."
    POINTS_HEADER = "Pontos"
    FILE_MENU = "Arquivo"
    EDIT_MENU = "Captura"
    VIEW_MENU = "Visualização"
    PROJECT_COUNTS = "{curves} curvas • {documents} documentos"
    SHORT_HELP = "1. Abra um documento\n2. Crie e calibre uma curva\n3. Capture os pontos e grave\n4. Exporte ou salve o projeto"
    PROJECT_FILTER = "Projeto de curvas (*.ecp)"
    PROJECT_SAVED = "Projeto salvo."
    UNSAVED = "O projeto tem alterações não salvas. Deseja salvá-las antes de continuar?"
    PROVENANCE = "Procedência e dataset"
    MANUFACTURER = "Fabricante"
    MODEL = "Modelo"
    NOTES = "Observação"
    RESTRICTED = "Material com uso restrito"
    TRACKING_FAILED = "Os arquivos de exportação foram gravados, mas o dataset falhou.\n{detail}"
    PREFERENCES = "Preferências…"
    APPEARANCE = "Aparência"
    EXPORT_SETTINGS = "Exportação e arquivos"
    SHORTCUTS = "Atalhos"
    THEME = "Tema"
    FONT_COLOR = "Cor do texto (auto ou #RRGGBB)"
    FONT_COLOR_HINT = "auto usa #202B38 no tema claro e #E3EDF6 no escuro. Informe #RRGGBB para ajustar manualmente."
    LIGHT = "Claro"
    DARK = "Escuro"
    SYSTEM = "Sistema"
    CANVAS_COLOR = "Fundo do canvas"
    AXIS_COLOR = "Cor dos eixos"
    AXIS_WIDTH = "Espessura dos eixos"
    AXIS_SIZE = "Tamanho do marcador de eixo"
    PALETTE = "Paleta (cores separadas por vírgula)"
    RESTORE = "Restaurar padrões"
    DATASET_ROOT = "Pasta do dataset"
    MAGNIFIER = "Lupa de precisão"
    MAGNIFIER_FACTOR = "Ampliação da lupa"
    ZOOM_IN = "Ampliar"
    ZOOM_OUT = "Reduzir"
    SAVE_PROJECT = "Salvar projeto…"
    NEW_PROJECT = "Novo projeto"
    OPEN_PROJECT = "Abrir projeto…"
    KEY_INVALID = "Verifique as cores e os atalhos. Não use atalhos repetidos."
    DUPLICATE = "Duplicar calibração anterior"
    DELETE = "Excluir"
    DELETE_QUESTION = "Excluir a curva inteira? Esta ação não pode ser desfeita."
    MAIN = "Principal"
    NAME = "Nome"
    INCLUDE = "Incluir"
    DOMAIN = "Domínio X (mín. / máx. / pontos)"
    COLOR = "Cor"
    WIDTH = "Espessura"
    MARKER = "Marcador"
    CIRCLE = "Círculo"
    SQUARE = "Quadrado"
    TRIANGLE = "Triângulo"
    ASSISTED = "Assistido (Origem / X / Y)"
    FREE = "Livre (três pares X, Y)"
    MODE = "Calibração"
    LINEAR = "Linear"
    LOG = "Logarítmico"
    X_SCALE = "Escala X"
    Y_SCALE = "Escala Y"
    X_VALUE = "Valor X"
    Y_VALUE = "Valor Y"
    BASE = "Base X"
    MAIN_X = "Pontos da curva principal"
    UNIFORM_X = "Malha uniforme"
    COUNT = "Quantidade de pontos"
    METHOD = "Interpolação"
    PROFILE = "Perfil"
    FORMAT = "Formato"
    BOTH = "CSV e XLSX"
    DESTINATION = "Destino"
    CHOOSE_DESTINATION = "Escolher destino da exportação"
    BROWSE = "Escolher…"
    RAW = "Incluir pontos brutos"
    RAW_ONLY = "Exportar somente pontos brutos"
    X_LABEL = "Rótulo da primeira coluna"
    DECIMAL = "Separador decimal"
    DELIMITER = "Separador de campo"
    BOM = "UTF-8 com BOM"
    TRACKING = "Registrar extrações no dataset"
    MISSING = "{rows} linhas incompletas. Colunas: {columns}."
    OUTPUT_FILES = "Arquivos gravados:\n{files}"
    NO_CURVES = "Grave pelo menos uma curva antes de exportar."
    NONE = "Sem curva (campo vazio)"
    AXIS_RECORD = "Ponto {number}: pixel ({px:.2f}, {py:.2f}) → ({vx:g}, {vy:g})"
    GEOMETRY_LOCKED = "Geometria gravada e protegida"
    CURVE_OPACITY = "Opacidade das curvas gravadas"
    AXIS_OPACITY = "Opacidade dos eixos inativos"
    IMAGE_OPACITY = "Opacidade da imagem"
    APP = "Extrator de Curvas MK2"
    OPEN = "Abrir documento…"
    CREATE = "Criar curva"
    SAVE_CURVE = "Gravar curva"
    EXPORT = "Exportar…"
    DISCARD = "Descartar curva"
    UNDO = "Desfazer ponto"
    REDO = "Refazer ponto"
    FIT = "Ajustar à janela"
    ACTUAL = "Tamanho original"
    CURVES = "CURVAS"
    EMPTY = "Abra uma imagem para começar\nCalibre três pontos e clique sobre a curva."
    FILTER = "Documentos (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.pdf *.ecp)"
    PAGES = "Selecionar páginas"
    SELECT_ALL = "Selecionar todas"
    PAGE = "Página {number}"
    PREVIOUS = "Página anterior"
    NEXT = "Próxima página"
    PASTE = "Colar imagem ou arquivo"
    DPI = "Resolução de PDF (DPI)"
    DPI_NOTE = "A nova resolução vale para os próximos documentos. Recarregar uma página exige nova calibração."
    NO_CLIPBOARD = "A área de transferência não contém uma imagem ou caminho de arquivo."
    CSV_FILTER = "CSV (*.csv)"
    CURVE_NAME = "Curva {number}"
    POINTS = "{count} pontos"
    IDLE = "Ocioso • Crie uma curva para iniciar."
    CAPTURE = "Captura • Clique para adicionar ponto. Direito / Enter: gravar curva."
    AXIS = "Calibração {number}/3 • Clique no ponto. Direito / Enter: confirmar etapa."
    ORIGIN = "Origem"
    X_AXIS = "Eixo X"
    Y_AXIS = "Eixo Y"
    X_MIN = "X mínimo"
    Y_MIN = "Y mínimo"
    X_MAX = "X máximo"
    Y_MAX = "Y máximo"
    OK = "Confirmar"
    CANCEL = "Cancelar"
    ERROR = "Não foi possível concluir"
    DONE = "Exportação concluída"
    DISCARD_QUESTION = "Descartar todos os pontos da curva em captura?"
    ACTIVE = "Grave ou descarte a curva em captura antes de continuar."
    OPEN_FIRST = "Abra um documento antes de criar uma curva."
    ONE_CURVE = "Esta etapa permite uma curva. Abra outra imagem para reiniciar."
    CONFIRM = "Confirmar ação"
    INVALID_NUMBER = "Informe um número válido (vírgula ou ponto decimal)."
    GENERIC_ERROR = "Ocorreu um erro. Detalhes técnicos foram registrados no arquivo de log."
    IO_ERROR = "Verifique o arquivo, o espaço disponível e a permissão de acesso.\n{detail}"


def domain_message(error):
    messages = {
        "locked": "A geometria desta curva já foi gravada. Exclua a curva e refaça a captura.",
        "empty_curve": "Adicione pelo menos um ponto antes de gravar.",
        "calibration_count": "Informe os três pontos de calibração.",
        "scale": "Escolha eixos lineares ou logarítmicos.",
        "finite": "Todos os valores precisam ser números finitos.",
        "degenerate": "Os pontos de calibração ou seus valores formam um sistema degenerado.",
        "log_positive": "Eixos logarítmicos exigem valores maiores que zero.",
        "few_points": "A curva {curve} precisa de pelo menos dois pontos para interpolação.",
        "nonmonotonic": "A curva {curve} dobra ou repete X no ponto {point}. Exporte os pontos brutos.",
        "method": "Método de interpolação inválido.",
        "main_curve": "Selecione uma curva principal entre as curvas incluídas.",
        "grid_count": "A malha precisa ter pelo menos dois pontos.",
        "separators": "Separadores inválidos: decimal e campo devem ser diferentes.",
        "profile_columns": "Associe as curvas às colunas do perfil escolhido.",
        "settings_invalid": "O arquivo de preferências contém valores inválidos.",
        "shortcuts_duplicate": "Cada atalho deve ser associado a uma única ação.",
        "dpi": "A resolução do PDF deve estar entre 72 e 600 DPI.",
        "missing_page": "A página de origem desta curva não está disponível.",
        "image_invalid": "O conteúdo recebido não é uma imagem válida.",
        "capture_active": T.ACTIVE,
        "project_version": "A versão deste projeto não é suportada.",
        "project_invalid": "O arquivo de projeto está incompleto ou inválido.",
        "dataset_conflict": "O arquivo do dataset pertence a outro documento.",
        "dataset_dpi": "Esta página já existe no dataset com outra rasterização. Escolha outra raiz.",
        "destination": T.DESTINATION_INVALID,
        "format": "Selecione CSV, XLSX ou ambos.",
    }
    return messages.get(error.code, T.GENERIC_ERROR).format(**error.details)

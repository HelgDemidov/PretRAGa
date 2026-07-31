# Схемы карты PretRAGa

СГЕНЕРИРОВАНО из `entity_map.yaml` скриптом `entity_map_build.py` — руками
не править. Цифры, таблицы и реестры — в [карте](entity_map.md); определения
прозой — в [словаре](entity_glossary.md).

**Смотреть в предпросмотре:** `Ctrl+Shift+V` во вкладке или `Ctrl+K V` сбоку.
В самом редакторе mermaid остаётся текстом — так и должно быть. Отдельного
расширения не нужно: рендер встроен в VS Code начиная с 1.121.

## Слои и направление зависимости

Метка ребра — сколько связей класса `dependency` пересекает границу слоёв.
Ребро вверх по стеку — ошибка сборки.

```mermaid
flowchart TD
    synthesis["0 — Мастерская синтеза"]
    query["1 — Слой запросов"]
    enrichment["2 — Обогащение"]
    curation["3 — Триаж и дедупликация"]
    registry["4 — Реестр корпуса"]
    conversion["5 — Конвертация"]
    acquisition["6 — Добыча"]
    foundation["7 — Сквозное основание"]
    acquisition -- "1" --> foundation
    conversion -- "1" --> acquisition
    enrichment -- "1" --> foundation
    curation -- "1" --> acquisition
    curation -- "1" --> conversion
    enrichment -- "1" --> conversion
    enrichment -- "1" --> enrichment
    query -- "4" --> enrichment
    query -- "1" --> registry
    query -- "2" --> foundation
    synthesis -- "1" --> conversion
```

## Сводная межгрупповая схема

Группы как узлы; метка ребра — число связей, пересекающих границу групп.

```mermaid
flowchart LR
    acquisition["Добыча"]
    content["Документ и содержимое"]
    facts_graph["Факты и граф"]
    storage["Реестр и хранение"]
    processes["Процессы"]
    query_synthesis["Запросы и синтез"]
    cross_cutting["Сквозное"]
    acquisition -- "1" --> content
    acquisition -- "1" --> cross_cutting
    content -- "3" --> acquisition
    content -- "3" --> storage
    content -- "1" --> facts_graph
    facts_graph -- "5" --> content
    facts_graph -- "1" --> acquisition
    facts_graph -- "3" --> storage
    acquisition -- "2" --> storage
    storage -- "2" --> content
    processes -- "7" --> content
    processes -- "4" --> facts_graph
    processes -- "2" --> storage
    processes -- "1" --> cross_cutting
    processes -- "1" --> acquisition
    query_synthesis -- "6" --> storage
    query_synthesis -- "3" --> facts_graph
    query_synthesis -- "2" --> content
    query_synthesis -- "1" --> cross_cutting
    cross_cutting -- "1" --> storage
```

## Проекции по группам

Сущности группы — в рамке; скруглённые узлы — соседи из других групп;
показаны все связи, касающиеся группы.

### Добыча

```mermaid
flowchart LR
    subgraph acquisition["Добыча"]
        Connector["Коннектор"]
        AcquisitionChannel["Канал добычи"]
        AcquisitionAct["Акт добычи"]
        RawPayload["Сырой payload"]
        AcquisitionHint["Подсказка добычи"]
    end
    Document(["Документ"])
    NetworkClient(["Сетевой клиент"])
    ContentVersion(["Версия содержимого"])
    ConversionRecord(["Запись конвертации"])
    TypedReference(["Типизированная ссылка"])
    Workspace(["Рабочее пространство"])
    MachineStore(["Машинное хранилище"])
    Triage(["Триаж"])
    AcquisitionChannel -- "экземпляр типа" --> Connector
    AcquisitionChannel -- "порождает" --> AcquisitionAct
    AcquisitionAct -- "приносит" --> RawPayload
    AcquisitionAct -- "вводит кандидата" --> Document
    AcquisitionAct -- "скачивает через" --> NetworkClient
    AcquisitionHint -- "питает пере-наполнение" --> AcquisitionChannel
    ContentVersion -- "payload" --> RawPayload
    ConversionRecord -- "из сырья" --> RawPayload
    Document -- "провенанс канала" --> AcquisitionChannel
    TypedReference -- "висячая порождает" --> AcquisitionHint
    RawPayload -- "живёт в" --> Workspace
    AcquisitionAct -- "хранится в" --> MachineStore
    Triage -- "судит после скачивания" --> RawPayload
```

### Документ и содержимое

```mermaid
flowchart LR
    subgraph content["Документ и содержимое"]
        Document["Документ"]
        ContentVersion["Версия содержимого"]
        CanonicalText["Канонический текст"]
        ConversionRecord["Запись конвертации"]
        ProvenanceAnchor["Якорь провенанса"]
        Fragment["Фрагмент"]
        Translation["Перевод"]
    end
    AcquisitionAct(["Акт добычи"])
    RawPayload(["Сырой payload"])
    CorpusRegistry(["Реестр корпуса"])
    ControlledVocabulary(["Контролируемый словарь"])
    AuthorityRuleTable(["Таблица авторитетности"])
    AcquisitionChannel(["Канал добычи"])
    Claim(["Утверждение"])
    TypedReference(["Типизированная ссылка"])
    GraphLayer(["Граф"])
    MachineStore(["Машинное хранилище"])
    VectorIndex(["Векторный индекс"])
    LexicalIndex(["Лексический индекс"])
    AdmissionMinimum(["Минимум приёмки"])
    Triage(["Триаж"])
    MergeOperation(["Склейка"])
    Enrichment(["Обогащение"])
    QueryLayer(["Слой запросов"])
    DeliverableValidator(["Валидатор деливерабла"])
    AcquisitionAct -- "вводит кандидата" --> Document
    Document -- "имеет версии" --> ContentVersion
    ContentVersion -- "payload" --> RawPayload
    ContentVersion -- "канонизируется в" --> CanonicalText
    CanonicalText -- "произведён по" --> ConversionRecord
    ConversionRecord -- "из сырья" --> RawPayload
    CanonicalText -- "нарезается на" --> Fragment
    CanonicalText -- "адресуется" --> ProvenanceAnchor
    Fragment -- "несёт интервал" --> ProvenanceAnchor
    Translation -- "линза над" --> ContentVersion
    Document -- "записан в" --> CorpusRegistry
    Document -- "классифицируется по" --> ControlledVocabulary
    AuthorityRuleTable -- "вычисляет класс" --> Document
    Document -- "провенанс канала" --> AcquisitionChannel
    ProvenanceAnchor -- "версия в тройке" --> ContentVersion
    Claim -- "заякорено" --> ProvenanceAnchor
    TypedReference -- "связывает документы" --> Document
    TypedReference -- "якорь текстовой находки" --> ProvenanceAnchor
    GraphLayer -- "узлы-работы" --> Document
    ConversionRecord -- "хранится в" --> MachineStore
    VectorIndex -- "индексирует" --> Fragment
    LexicalIndex -- "индексирует" --> CanonicalText
    ProvenanceAnchor -- "хранится в" --> MachineStore
    AdmissionMinimum -- "ворота приёмки" --> Document
    Triage -- "выносит вердикт" --> Document
    MergeOperation -- "объединяет" --> Document
    Enrichment -- "производит" --> Translation
    Triage -- "и после конвертации" --> CanonicalText
    Enrichment -- "единица пере-деривации" --> ContentVersion
    Enrichment -- "единица дорогого перерасчёта" --> Fragment
    QueryLayer -- "выдаёт" --> ProvenanceAnchor
    DeliverableValidator -- "разрешает" --> ProvenanceAnchor
```

### Факты и граф

```mermaid
flowchart LR
    subgraph facts_graph["Факты и граф"]
        Claim["Утверждение"]
        TypedReference["Типизированная ссылка"]
        WorldEntity["Сущность мира"]
        ControlledVocabulary["Контролируемый словарь"]
        AuthorityRuleTable["Таблица авторитетности"]
        GraphLayer["Граф"]
        VerbalizedGraphContext["Словесная обвязка"]
    end
    Document(["Документ"])
    ProvenanceAnchor(["Якорь провенанса"])
    AcquisitionHint(["Подсказка добычи"])
    VectorIndex(["Векторный индекс"])
    MachineStore(["Машинное хранилище"])
    DerivationManifest(["Манифест деривации"])
    Enrichment(["Обогащение"])
    QueryLayer(["Слой запросов"])
    TrendQuery(["Запрос тренда"])
    Deliverable(["Деливерабл"])
    Document -- "классифицируется по" --> ControlledVocabulary
    AuthorityRuleTable -- "вычисляет класс" --> Document
    Claim -- "заякорено" --> ProvenanceAnchor
    Claim -- "упоминает" --> WorldEntity
    Claim -- "темы и предикаты из" --> ControlledVocabulary
    TypedReference -- "связывает документы" --> Document
    TypedReference -- "якорь текстовой находки" --> ProvenanceAnchor
    TypedReference -- "типы из" --> ControlledVocabulary
    TypedReference -- "висячая порождает" --> AcquisitionHint
    GraphLayer -- "рёбра из" --> Claim
    GraphLayer -- "рёбра из" --> TypedReference
    GraphLayer -- "узлы" --> WorldEntity
    GraphLayer -- "узлы-работы" --> Document
    GraphLayer -- "мета-словари" --> ControlledVocabulary
    VerbalizedGraphContext -- "черпает из" --> GraphLayer
    VerbalizedGraphContext -- "вход эмбеддинга" --> VectorIndex
    Claim -- "хранится в" --> MachineStore
    GraphLayer -- "несёт" --> DerivationManifest
    Enrichment -- "извлекает" --> Claim
    Enrichment -- "извлекает" --> TypedReference
    Enrichment -- "генерирует" --> VerbalizedGraphContext
    Enrichment -- "строит" --> GraphLayer
    QueryLayer -- "расширяет по (PPR)" --> GraphLayer
    TrendQuery -- "считает" --> Claim
    Deliverable -- "ссылка на улику" --> Claim
```

### Реестр и хранение

```mermaid
flowchart LR
    subgraph storage["Реестр и хранение"]
        CorpusRegistry["Реестр корпуса"]
        MachineStore["Машинное хранилище"]
        VectorIndex["Векторный индекс"]
        LexicalIndex["Лексический индекс"]
        DerivationManifest["Манифест деривации"]
        Corpus["Корпус"]
        Workspace["Рабочее пространство"]
    end
    Document(["Документ"])
    VerbalizedGraphContext(["Словесная обвязка"])
    RawPayload(["Сырой payload"])
    AcquisitionAct(["Акт добычи"])
    ConversionRecord(["Запись конвертации"])
    Claim(["Утверждение"])
    Fragment(["Фрагмент"])
    CanonicalText(["Канонический текст"])
    GraphLayer(["Граф"])
    ProvenanceAnchor(["Якорь провенанса"])
    Enrichment(["Обогащение"])
    QueryLayer(["Слой запросов"])
    Deliverable(["Деливерабл"])
    WriterLock(["Замок писателя"])
    Document -- "записан в" --> CorpusRegistry
    VerbalizedGraphContext -- "вход эмбеддинга" --> VectorIndex
    Corpus -- "предикат над" --> CorpusRegistry
    CorpusRegistry -- "живёт в" --> Workspace
    RawPayload -- "живёт в" --> Workspace
    MachineStore -- "живёт в" --> Workspace
    AcquisitionAct -- "хранится в" --> MachineStore
    ConversionRecord -- "хранится в" --> MachineStore
    Claim -- "хранится в" --> MachineStore
    VectorIndex -- "индексирует" --> Fragment
    LexicalIndex -- "индексирует" --> CanonicalText
    VectorIndex -- "несёт" --> DerivationManifest
    LexicalIndex -- "несёт" --> DerivationManifest
    GraphLayer -- "несёт" --> DerivationManifest
    DerivationManifest -- "коммит реестра" --> CorpusRegistry
    ProvenanceAnchor -- "хранится в" --> MachineStore
    VectorIndex -- "живёт в" --> Workspace
    LexicalIndex -- "живёт в" --> Workspace
    Enrichment -- "строит" --> VectorIndex
    Enrichment -- "строит" --> LexicalIndex
    QueryLayer -- "читает" --> VectorIndex
    QueryLayer -- "читает" --> LexicalIndex
    QueryLayer -- "сверяет свежесть" --> CorpusRegistry
    Deliverable -- "штампуется" --> DerivationManifest
    Deliverable -- "живёт в" --> Workspace
    QueryLayer -- "сверяет свежесть по" --> DerivationManifest
    WriterLock -- "охраняет" --> Workspace
```

### Процессы

```mermaid
flowchart LR
    subgraph processes["Процессы"]
        AdmissionMinimum["Минимум приёмки"]
        Triage["Триаж"]
        Deduplication["Дедупликация"]
        MergeOperation["Склейка"]
        Enrichment["Обогащение"]
        ExceptionQueue["Очередь исключений"]
        Reconciliation["Реконсиляция"]
    end
    Document(["Документ"])
    Claim(["Утверждение"])
    TypedReference(["Типизированная ссылка"])
    Translation(["Перевод"])
    VerbalizedGraphContext(["Словесная обвязка"])
    VectorIndex(["Векторный индекс"])
    LexicalIndex(["Лексический индекс"])
    GraphLayer(["Граф"])
    NetworkClient(["Сетевой клиент"])
    RawPayload(["Сырой payload"])
    CanonicalText(["Канонический текст"])
    ContentVersion(["Версия содержимого"])
    Fragment(["Фрагмент"])
    AdmissionMinimum -- "ворота приёмки" --> Document
    Triage -- "выносит вердикт" --> Document
    Triage -- "направляет" --> ExceptionQueue
    Deduplication -- "предлагает" --> MergeOperation
    MergeOperation -- "объединяет" --> Document
    Enrichment -- "извлекает" --> Claim
    Enrichment -- "извлекает" --> TypedReference
    Enrichment -- "производит" --> Translation
    Enrichment -- "генерирует" --> VerbalizedGraphContext
    Enrichment -- "строит" --> VectorIndex
    Enrichment -- "строит" --> LexicalIndex
    Enrichment -- "строит" --> GraphLayer
    Enrichment -- "направляет" --> ExceptionQueue
    Enrichment -- "вызывает" --> NetworkClient
    Reconciliation -- "пере-триаж" --> Triage
    Reconciliation -- "пере-предлагает" --> Deduplication
    Reconciliation -- "правит" --> Enrichment
    Triage -- "судит после скачивания" --> RawPayload
    Triage -- "и после конвертации" --> CanonicalText
    Enrichment -- "единица пере-деривации" --> ContentVersion
    Enrichment -- "единица дорогого перерасчёта" --> Fragment
```

### Запросы и синтез

```mermaid
flowchart LR
    subgraph query_synthesis["Запросы и синтез"]
        QueryLayer["Слой запросов"]
        TrendQuery["Запрос тренда"]
        Deliverable["Деливерабл"]
        DeliverableValidator["Валидатор деливерабла"]
    end
    VectorIndex(["Векторный индекс"])
    LexicalIndex(["Лексический индекс"])
    GraphLayer(["Граф"])
    CorpusRegistry(["Реестр корпуса"])
    ProvenanceAnchor(["Якорь провенанса"])
    NetworkClient(["Сетевой клиент"])
    Claim(["Утверждение"])
    DerivationManifest(["Манифест деривации"])
    Workspace(["Рабочее пространство"])
    QueryLayer -- "читает" --> VectorIndex
    QueryLayer -- "читает" --> LexicalIndex
    QueryLayer -- "расширяет по (PPR)" --> GraphLayer
    QueryLayer -- "сверяет свежесть" --> CorpusRegistry
    QueryLayer -- "выдаёт" --> ProvenanceAnchor
    QueryLayer -- "эмбеддинг вопроса" --> NetworkClient
    TrendQuery -- "считает" --> Claim
    Deliverable -- "штампуется" --> DerivationManifest
    Deliverable -- "живёт в" --> Workspace
    DeliverableValidator -- "проверяет" --> Deliverable
    DeliverableValidator -- "разрешает" --> ProvenanceAnchor
    QueryLayer -- "сверяет свежесть по" --> DerivationManifest
    Deliverable -- "ссылка на улику" --> Claim
```

### Сквозное

```mermaid
flowchart LR
    subgraph cross_cutting["Сквозное"]
        NetworkClient["Сетевой клиент"]
        WriterLock["Замок писателя"]
    end
    AcquisitionAct(["Акт добычи"])
    Enrichment(["Обогащение"])
    QueryLayer(["Слой запросов"])
    Workspace(["Рабочее пространство"])
    AcquisitionAct -- "скачивает через" --> NetworkClient
    Enrichment -- "вызывает" --> NetworkClient
    QueryLayer -- "эмбеддинг вопроса" --> NetworkClient
    WriterLock -- "охраняет" --> Workspace
```

## Полный граф связей

```mermaid
flowchart LR
    subgraph acquisition["Добыча"]
        Connector["Коннектор"]
        AcquisitionChannel["Канал добычи"]
        AcquisitionAct["Акт добычи"]
        RawPayload["Сырой payload"]
        AcquisitionHint["Подсказка добычи"]
    end
    subgraph content["Документ и содержимое"]
        Document["Документ"]
        ContentVersion["Версия содержимого"]
        CanonicalText["Канонический текст"]
        ConversionRecord["Запись конвертации"]
        ProvenanceAnchor["Якорь провенанса"]
        Fragment["Фрагмент"]
        Translation["Перевод"]
    end
    subgraph facts_graph["Факты и граф"]
        Claim["Утверждение"]
        TypedReference["Типизированная ссылка"]
        WorldEntity["Сущность мира"]
        ControlledVocabulary["Контролируемый словарь"]
        AuthorityRuleTable["Таблица авторитетности"]
        GraphLayer["Граф"]
        VerbalizedGraphContext["Словесная обвязка"]
    end
    subgraph storage["Реестр и хранение"]
        CorpusRegistry["Реестр корпуса"]
        MachineStore["Машинное хранилище"]
        VectorIndex["Векторный индекс"]
        LexicalIndex["Лексический индекс"]
        DerivationManifest["Манифест деривации"]
        Corpus["Корпус"]
        Workspace["Рабочее пространство"]
    end
    subgraph processes["Процессы"]
        AdmissionMinimum["Минимум приёмки"]
        Triage["Триаж"]
        Deduplication["Дедупликация"]
        MergeOperation["Склейка"]
        Enrichment["Обогащение"]
        ExceptionQueue["Очередь исключений"]
        Reconciliation["Реконсиляция"]
    end
    subgraph query_synthesis["Запросы и синтез"]
        QueryLayer["Слой запросов"]
        TrendQuery["Запрос тренда"]
        Deliverable["Деливерабл"]
        DeliverableValidator["Валидатор деливерабла"]
    end
    subgraph cross_cutting["Сквозное"]
        NetworkClient["Сетевой клиент"]
        WriterLock["Замок писателя"]
    end
    AcquisitionChannel -- "экземпляр типа" --> Connector
    AcquisitionChannel -- "порождает" --> AcquisitionAct
    AcquisitionAct -- "приносит" --> RawPayload
    AcquisitionAct -- "вводит кандидата" --> Document
    AcquisitionAct -- "скачивает через" --> NetworkClient
    AcquisitionHint -- "питает пере-наполнение" --> AcquisitionChannel
    Document -- "имеет версии" --> ContentVersion
    ContentVersion -- "payload" --> RawPayload
    ContentVersion -- "канонизируется в" --> CanonicalText
    CanonicalText -- "произведён по" --> ConversionRecord
    ConversionRecord -- "из сырья" --> RawPayload
    CanonicalText -- "нарезается на" --> Fragment
    CanonicalText -- "адресуется" --> ProvenanceAnchor
    Fragment -- "несёт интервал" --> ProvenanceAnchor
    Translation -- "линза над" --> ContentVersion
    Document -- "записан в" --> CorpusRegistry
    Document -- "классифицируется по" --> ControlledVocabulary
    AuthorityRuleTable -- "вычисляет класс" --> Document
    Document -- "провенанс канала" --> AcquisitionChannel
    ProvenanceAnchor -- "версия в тройке" --> ContentVersion
    Claim -- "заякорено" --> ProvenanceAnchor
    Claim -- "упоминает" --> WorldEntity
    Claim -- "темы и предикаты из" --> ControlledVocabulary
    TypedReference -- "связывает документы" --> Document
    TypedReference -- "якорь текстовой находки" --> ProvenanceAnchor
    TypedReference -- "типы из" --> ControlledVocabulary
    TypedReference -- "висячая порождает" --> AcquisitionHint
    GraphLayer -- "рёбра из" --> Claim
    GraphLayer -- "рёбра из" --> TypedReference
    GraphLayer -- "узлы" --> WorldEntity
    GraphLayer -- "узлы-работы" --> Document
    GraphLayer -- "мета-словари" --> ControlledVocabulary
    VerbalizedGraphContext -- "черпает из" --> GraphLayer
    VerbalizedGraphContext -- "вход эмбеддинга" --> VectorIndex
    Corpus -- "предикат над" --> CorpusRegistry
    CorpusRegistry -- "живёт в" --> Workspace
    RawPayload -- "живёт в" --> Workspace
    MachineStore -- "живёт в" --> Workspace
    AcquisitionAct -- "хранится в" --> MachineStore
    ConversionRecord -- "хранится в" --> MachineStore
    Claim -- "хранится в" --> MachineStore
    VectorIndex -- "индексирует" --> Fragment
    LexicalIndex -- "индексирует" --> CanonicalText
    VectorIndex -- "несёт" --> DerivationManifest
    LexicalIndex -- "несёт" --> DerivationManifest
    GraphLayer -- "несёт" --> DerivationManifest
    DerivationManifest -- "коммит реестра" --> CorpusRegistry
    ProvenanceAnchor -- "хранится в" --> MachineStore
    VectorIndex -- "живёт в" --> Workspace
    LexicalIndex -- "живёт в" --> Workspace
    AdmissionMinimum -- "ворота приёмки" --> Document
    Triage -- "выносит вердикт" --> Document
    Triage -- "направляет" --> ExceptionQueue
    Deduplication -- "предлагает" --> MergeOperation
    MergeOperation -- "объединяет" --> Document
    Enrichment -- "извлекает" --> Claim
    Enrichment -- "извлекает" --> TypedReference
    Enrichment -- "производит" --> Translation
    Enrichment -- "генерирует" --> VerbalizedGraphContext
    Enrichment -- "строит" --> VectorIndex
    Enrichment -- "строит" --> LexicalIndex
    Enrichment -- "строит" --> GraphLayer
    Enrichment -- "направляет" --> ExceptionQueue
    Enrichment -- "вызывает" --> NetworkClient
    Reconciliation -- "пере-триаж" --> Triage
    Reconciliation -- "пере-предлагает" --> Deduplication
    Reconciliation -- "правит" --> Enrichment
    Triage -- "судит после скачивания" --> RawPayload
    Triage -- "и после конвертации" --> CanonicalText
    Enrichment -- "единица пере-деривации" --> ContentVersion
    Enrichment -- "единица дорогого перерасчёта" --> Fragment
    QueryLayer -- "читает" --> VectorIndex
    QueryLayer -- "читает" --> LexicalIndex
    QueryLayer -- "расширяет по (PPR)" --> GraphLayer
    QueryLayer -- "сверяет свежесть" --> CorpusRegistry
    QueryLayer -- "выдаёт" --> ProvenanceAnchor
    QueryLayer -- "эмбеддинг вопроса" --> NetworkClient
    TrendQuery -- "считает" --> Claim
    Deliverable -- "штампуется" --> DerivationManifest
    Deliverable -- "живёт в" --> Workspace
    DeliverableValidator -- "проверяет" --> Deliverable
    DeliverableValidator -- "разрешает" --> ProvenanceAnchor
    QueryLayer -- "сверяет свежесть по" --> DerivationManifest
    Deliverable -- "ссылка на улику" --> Claim
    WriterLock -- "охраняет" --> Workspace
```

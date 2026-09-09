# Extração estruturada de laudos

## Endpoint

`POST /api/extract/structured` recebe um upload `multipart/form-data` no campo `file` e devolve `application/json`. O `schema_version` atual é `"1.0"` e `document_type` é `"laudo"`.

O resultado tem este formato:

```json
{
  "schema_version": "1.0",
  "filename": "arquivo.pdf",
  "page_count": 1,
  "document_type": "laudo",
  "fields": {
    "produto": "...",
    "lote": "...",
    "data": "...",
    "nota_fiscal": "...",
    "data_fabricacao": "...",
    "data_validade": "...",
    "embalagem": null,
    "quantidade": "...",
    "fornecedor": "...",
    "transportadora": null,
    "cliente": null
  },
  "tables": [
    {
      "section": "...",
      "columns": ["especificacao", "parametro", "resultado"],
      "rows": [{"especificacao": "...", "parametro": "...", "resultado": "..."}]
    }
  ],
  "warnings": []
}
```

Todos os valores extraídos são strings ou `null`; datas, unidades, intervalos, números com vírgula e resultados como `3:11` não são convertidos. Campos ausentes ou vazios são `null`. `section` pode ser `null` quando a tabela não informa uma seção.

Há dois layouts conhecidos:

- O layout de três colunas é identificado pelos rótulos de coluna equivalentes a `ESPECIFICAÇÃO`, `PARAMETRO` e `RESULTADO`. O cabeçalho `CARACTERISTICAS ORGANOLEPTICAS` é uma pista de seção, aceita variações de acentos e espaços, e não é obrigatório para reconhecer o layout. Nos exemplos, a tabela contém as seções `CARACTERISTICAS ORGANOLEPTICAS` e `CARACTERISTICAS FISICO - QUIMICA`.
- O layout de cinco colunas usa `item`, `unidade`, `especificacoes`, `resultado` e `observacao`. Nos exemplos, a seção é `null`.

## Exemplo de três colunas

Entrada: `examples/2556.pdf`.

```json
{
  "schema_version": "1.0",
  "filename": "2556.pdf",
  "page_count": 1,
  "document_type": "laudo",
  "fields": {
    "produto": "TD PREMIUM IND 20 KG",
    "lote": "2026/137744",
    "data": "16/06/2026",
    "nota_fiscal": "77486",
    "data_fabricacao": "01/07/2026",
    "data_validade": "01/07/2028",
    "embalagem": "BB",
    "quantidade": "140 UND",
    "fornecedor": "REINIGEND QUIMICA DO BRASIL LTDA.",
    "transportadora": null,
    "cliente": null
  },
  "tables": [{
    "section": "CARACTERISTICAS ORGANOLEPTICAS",
    "columns": ["especificacao", "parametro", "resultado"],
    "rows": [
      {"especificacao": "FORMA PRODUTO", "parametro": "LIQUIDO VISCOSO", "resultado": "CONFERE"},
      {"especificacao": "COR", "parametro": "VERDE CROMACID", "resultado": "CONFERE"},
      {"especificacao": "ODOR", "parametro": "CARACTERISTICO", "resultado": "CONFERE"}
    ]
  }, {
    "section": "CARACTERISTICAS FISICO - QUIMICA",
    "columns": ["especificacao", "parametro", "resultado"],
    "rows": [
      {"especificacao": "DENSIDADE G/ML", "parametro": "1,02 A 1,04", "resultado": "1,04"},
      {"especificacao": "VISCOSIDADE(S)", "parametro": "ACIMA DE 1,2 MINUTOS", "resultado": "3:11"},
      {"especificacao": "PH PURO", "parametro": "10,0 A 10,8", "resultado": "10,5"},
      {"especificacao": "TEMPERATURA PRODUTO ºC", "parametro": "15 A 30", "resultado": "18,2"},
      {"especificacao": "TEMPERATURA AMBIENTE ºC", "parametro": "15 A 30", "resultado": "16,2"}
    ]
  }],
  "warnings": []
}
```

## Exemplo de cinco colunas

Entrada: `examples/1353.pdf`.

```json
{
  "schema_version": "1.0",
  "filename": "1353.pdf",
  "page_count": 1,
  "document_type": "laudo",
  "fields": {
    "produto": "REINI LAND 380 POS 05 L",
    "lote": "123/2026",
    "data": "30/06/2026",
    "nota_fiscal": "77708",
    "data_fabricacao": "09/07/2026",
    "data_validade": "09/07/2028",
    "embalagem": "BB",
    "quantidade": "30 UND",
    "fornecedor": "REINIGEND QUIMICA DO BRASIL LTDA.",
    "transportadora": null,
    "cliente": null
  },
  "tables": [{
    "section": null,
    "columns": ["item", "unidade", "especificacoes", "resultado", "observacao"],
    "rows": [
      {"item": "INSPEÇAO VISUAL", "unidade": null, "especificacoes": "LIQUIDO DE ALTA VISCOSIDADE", "resultado": "OK", "observacao": null},
      {"item": "COR", "unidade": null, "especificacoes": "VERDE ESCURO", "resultado": "OK", "observacao": null},
      {"item": "TEMP. AMBIENTE", "unidade": "°C", "especificacoes": "15 A 30", "resultado": "20,5", "observacao": null},
      {"item": "TEMP. PRODUTO", "unidade": "°C", "especificacoes": "15 A 30", "resultado": "21,8", "observacao": null},
      {"item": "PONTO DE FUSAO", "unidade": "°C", "especificacoes": "NÃO APLICÁVEL", "resultado": "-", "observacao": null},
      {"item": "SOLUBILIDADE", "unidade": "m/Vol", "especificacoes": "NÃO APLICÁVEL", "resultado": "-", "observacao": null},
      {"item": "PH", "unidade": null, "especificacoes": "2,0 - 2,5", "resultado": "2,5", "observacao": null},
      {"item": "DENSIDADE", "unidade": "g/ml", "especificacoes": "1,04 - 1,07", "resultado": "1,05", "observacao": null},
      {"item": "VISCOSIDADE", "unidade": "s", "especificacoes": "NAO APLICÁVEL", "resultado": "-", "observacao": null}
    ]
  }],
  "warnings": []
}
```

## Clientes

```bash
curl -sS -X POST http://127.0.0.1:8000/api/extract/structured \
  -F 'file=@examples/laudo.pdf'
```

```python
from pathlib import Path
import requests

with Path("examples/3555.pdf").open("rb") as pdf:
    response = requests.post(
        "http://127.0.0.1:8000/api/extract/structured",
        files={"file": ("3555.pdf", pdf, "application/pdf")},
        timeout=60,
    )
response.raise_for_status()
document = response.json()
print(document["fields"]["produto"])
```

## Erros, limites e heurísticas

O limite do upload é 25 MB e o PDF é processado em memória. Arquivos que não terminam em `.pdf`, não começam com uma assinatura PDF válida, estão protegidos por senha ou não podem ser interpretados retornam erro HTTP (normalmente `415` ou `422`); o limite excedido retorna `413`. PDFs que só contêm imagens precisam de OCR antes do envio.

O parser identifica rótulos do cabeçalho sem depender da posição exata, normaliza maiúsculas, acentos, espaços e pontuação, separa valores pelos próximos rótulos conhecidos e recompõe valores quebrados em várias linhas. Os valores dos campos de cabeçalho terminam antes do início de uma tabela ou do rodapé, mesmo quando o layout da tabela não é reconhecido. O layout é escolhido pelos rótulos de coluna; os títulos de seção ajudam a nomear a seção, mas não são obrigatórios. Um PDF cujo texto foi achatado sem coordenadas suficientes pode retornar os campos e warnings, mas não permite garantir a reconstrução completa da tabela. Cabeçalhos desconhecidos ou danificados geram warning e não têm valores inferidos. Quando nenhuma tabela é identificada, `warnings` contém uma observação; em PDFs com estrutura incompleta, revise também campos `null` e linhas retornadas. O resultado é heurístico e não garante interpretação de qualquer PDF arbitrário; valide dados críticos.

Um trecho de texto copiado do PDF pode ser usado para testar a extração dos campos, mas não substitui o PDF original para validar a tabela: a separação das colunas depende da geometria das palavras no documento.

A implementação fica em `backend/app/structured_parser.py` e `backend/app/structured_geometry.py`. Para adicionar aliases de campos, altere o mapa de aliases do parser; para incluir uma variação de layout, estenda a detecção e a separação de colunas na camada de geometria, mantendo as chaves canônicas do contrato. Acrescente um fixture de aceitação em `backend/tests/test_structured_acceptance.py` para cada nova variação.

## Respostas HTTP e documentação interativa

| Status | Situação |
|---|---|
| `200` | PDF processado; o JSON pode conter campos `null` ou warnings heurísticos. |
| `413` | Upload acima de 25 MB. |
| `415` | Extensão diferente de `.pdf` ou assinatura de arquivo inválida. |
| `422` | PDF protegido por senha, ilegível ou sem texto selecionável (OCR necessário). |

O Swagger/OpenAPI está disponível em [`/api/docs`](http://127.0.0.1:8000/api/docs), e o esquema JSON em [`/openapi.json`](http://127.0.0.1:8000/openapi.json).

Para adicionar uma variação, inclua o novo alias normalizado no parser, mapeie seus rótulos para uma chave canônica e acrescente um PDF fixture representativo. Execute os testes do backend e do frontend após a alteração:

```bash
python -m compileall backend/app
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
npm test
```

O comando de `unittest` pressupõe a suíte de testes do backend no diretório `backend/tests`. Em um ambiente novo, instale `python -m pip install -r backend/requirements-dev.txt`; esse arquivo inclui as dependências de produção e `httpx` para o `TestClient`.

O frontend permite alternar entre a extração textual existente (`/api/extract`) e a extração estruturada (`/api/extract/structured`) para testar ambos os contratos.

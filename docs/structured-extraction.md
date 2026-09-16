# Extração estruturada de laudos

`POST /api/extract/structured` recebe `multipart/form-data` no campo `file` e aceita arquivos PDF ou RTF de até 25 MB. Retorna JSON com os 11 campos do laudo na raiz e `tabelas`:

```json
{
  "produto": "...",
  "lote": "...",
  "data_fabricacao": "...",
  "nota_fiscal": "...",
  "data_le": "...",
  "data_validade": "...",
  "embalagem": null,
  "quantidade": "...",
  "fornecedor": "...",
  "transportadora": null,
  "cliente": null,
  "tabelas": [
    {
      "secao": null,
      "linhas": [
        {
          "item": "...",
          "unidade": null,
          "especificacoes": null,
          "resultado": null,
          "observacoes": null
        }
      ]
    }
  ]
}
```

Datas, unidades, intervalos, números e resultados permanecem strings; vazios são `null`. Cada linha contém todas as chaves da tabela, inclusive as colunas vazias. Em tabelas desconhecidas, exceto o layout canônico de cinco colunas, cabeçalhos viram chaves normalizadas (`nome do item` → `nome_do_item`); vazios usam `coluna_N` e colisões recebem sufixos (`item`, `item_2`).

Os layouts canônicos são `especificacao`, `parametro`, `resultado` (3 colunas) e `item`, `unidade`, `especificacoes`, `resultado`, `observacoes` (5 colunas). Na atribuição das cinco colunas, os valores são mapeados pela posição, nesta ordem; rótulos quebrados ou divergentes não mudam essa atribuição. Células ausentes permanecem `null`; o layout canônico de cinco colunas não usa nomes genéricos derivados dos rótulos. Para grades desalinhadas, a extração combina a geometria das células com os trechos de texto do cabeçalho, inclusive quando uma palavra atravessa uma separação; em tabelas sem bordas, as faixas são aprendidas da geometria do cabeçalho e verificadas contra as linhas de dados. Esses sinais podem ser insuficientes em PDFs achatados, digitalizados ou com sobreposição severa, portanto valide dados críticos.

## Exemplo de três colunas (`examples/2556.pdf`)

```json
{
  "produto": "TD PREMIUM IND 20 KG",
  "lote": "2026/137744",
  "data_le": "16/06/2026",
  "nota_fiscal": "77486",
  "data_fabricacao": "01/07/2026",
  "data_validade": "01/07/2028",
  "embalagem": "BB",
  "quantidade": "140 UND",
  "fornecedor": "REINIGEND QUIMICA DO BRASIL LTDA.",
  "transportadora": null,
  "cliente": null,
  "tabelas": [
    {
      "secao": "CARACTERISTICAS ORGANOLEPTICAS",
      "linhas": [
        {
          "especificacao": "FORMA PRODUTO",
          "parametro": "LIQUIDO VISCOSO",
          "resultado": "CONFERE"
        },
        {
          "especificacao": "COR",
          "parametro": "VERDE CROMACID",
          "resultado": "CONFERE"
        },
        {
          "especificacao": "ODOR",
          "parametro": "CARACTERISTICO",
          "resultado": "CONFERE"
        }
      ]
    },
    {
      "secao": "CARACTERISTICAS FISICO - QUIMICA",
      "linhas": [
        {
          "especificacao": "DENSIDADE G/ML",
          "parametro": "1,02 A 1,04",
          "resultado": "1,04"
        },
        {
          "especificacao": "VISCOSIDADE(S)",
          "parametro": "ACIMA DE 1,2 MINUTOS",
          "resultado": "3:11"
        },
        {
          "especificacao": "PH PURO",
          "parametro": "10,0 A 10,8",
          "resultado": "10,5"
        },
        {
          "especificacao": "TEMPERATURA PRODUTO ºC",
          "parametro": "15 A 30",
          "resultado": "18,2"
        },
        {
          "especificacao": "TEMPERATURA AMBIENTE ºC",
          "parametro": "15 A 30",
          "resultado": "16,2"
        }
      ]
    }
  ]
}
```

## Exemplo de cinco colunas (`examples/1353.pdf`)

```json
{
  "produto": "REINI LAND 380 POS 05 L",
  "lote": "123/2026",
  "data_le": "30/06/2026",
  "nota_fiscal": "77708",
  "data_fabricacao": "09/07/2026",
  "data_validade": "09/07/2028",
  "embalagem": "BB",
  "quantidade": "30 UND",
  "fornecedor": "REINIGEND QUIMICA DO BRASIL LTDA.",
  "transportadora": null,
  "cliente": null,
  "tabelas": [
    {
      "secao": null,
      "linhas": [
        {
          "item": "INSPEÇAO VISUAL",
          "unidade": null,
          "especificacoes": "LIQUIDO DE ALTA VISCOSIDADE",
          "resultado": "OK",
          "observacoes": null
        },
        {
          "item": "COR",
          "unidade": null,
          "especificacoes": "VERDE ESCURO",
          "resultado": "OK",
          "observacoes": null
        },
        {
          "item": "TEMP. AMBIENTE",
          "unidade": "°C",
          "especificacoes": "15 A 30",
          "resultado": "20,5",
          "observacoes": null
        },
        {
          "item": "TEMP. PRODUTO",
          "unidade": "°C",
          "especificacoes": "15 A 30",
          "resultado": "21,8",
          "observacoes": null
        },
        {
          "item": "PONTO DE FUSAO",
          "unidade": "°C",
          "especificacoes": "NÃO APLICÁVEL",
          "resultado": "-",
          "observacoes": null
        },
        {
          "item": "SOLUBILIDADE",
          "unidade": "m/Vol",
          "especificacoes": "NÃO APLICÁVEL",
          "resultado": "-",
          "observacoes": null
        },
        {
          "item": "PH",
          "unidade": null,
          "especificacoes": "2,0 - 2,5",
          "resultado": "2,5",
          "observacoes": null
        },
        {
          "item": "DENSIDADE",
          "unidade": "g/ml",
          "especificacoes": "1,04 - 1,07",
          "resultado": "1,05",
          "observacoes": null
        },
        {
          "item": "VISCOSIDADE",
          "unidade": "s",
          "especificacoes": "NAO APLICÁVEL",
          "resultado": "-",
          "observacoes": null
        }
      ]
    }
  ]
}
```

## Uso e limites

```bash
curl --fail-with-body --show-error --max-time 120 -sS -X POST http://127.0.0.1:8000/api/extract/structured -F 'file=@examples/2556.pdf' | jq .
curl --fail-with-body --show-error --max-time 120 -sS -X POST http://127.0.0.1:8000/api/extract/structured -F 'file=@examples/Laudo241.322.rtf' | jq .
```

Em produção, use a URL pública após publicar a versão correspondente da API:

```bash
curl --fail-with-body --show-error --max-time 120 -sS -X POST https://pdfextratorapi.tclynkerp.com.br/api/extract/structured -F 'file=@examples/2556.pdf' | jq .
curl --fail-with-body --show-error --max-time 120 -sS -X POST https://pdfextratorapi.tclynkerp.com.br/api/extract -F 'file=@examples/2556.pdf' | jq .
```

```python
from pathlib import Path
import requests
with Path("examples/1353.pdf").open("rb") as pdf:
    response = requests.post("http://127.0.0.1:8000/api/extract/structured", files={"file": ("1353.pdf", pdf, "application/pdf")}, timeout=120)
response.raise_for_status()
print(response.json()["produto"])
```

Swagger: [`/api/docs`](http://127.0.0.1:8000/api/docs). OpenAPI: [`/openapi.json`](http://127.0.0.1:8000/openapi.json). O limite é 25 MB e a extração ocorre em memória; o framework pode usar spool temporário durante o multipart e o remove ao fim da requisição. Arquivo inválido retorna `415`, upload excedido `413` e documento protegido, ilegível ou sem texto extraível `422`; PDFs digitalizados precisam de OCR.

O protótipo anterior usava `fields.produto` e `tables[].rows`; agora são `produto` e `tabelas[].linhas`, e os metadados técnicos não fazem parte do JSON público. O endpoint textual `/api/extract` permanece separado e aceita PDF e RTF, retornando o documento lógico com `page_count` igual a 1 para RTF. As tabelas preservam os layouts canônicos de três e cinco colunas, com células vazias como `null`; RTF não é convertido por LibreOffice nem depende de runtime externo. O suporte RTF cobre a codificação padrão CP1252 e escapes Unicode `\u`; arquivos que declaram outra página de código ANSI podem retornar `422`.

## Concorrência

O processamento usa um pool dedicado dimensionado automaticamente a partir dos recursos de CPU e memória disponíveis no processo e no container. A configuração acompanha o ambiente, sem exigir ajuste manual de workers. Em sobrecarga extrema, a fila aplica backpressure: quando não há capacidade disponível dentro do prazo, a API responde `503` com `Retry-After`; quando o processamento excede seu prazo, responde `504`. Um processo que já começou continua ocupando seu slot até terminar.

O dimensionamento é por processo e respeita os limites de CPU e memória do container; não limita conexões de rede nem o spool temporário do framework. Depois de alterar o código, faça o deploy da nova imagem/versão da API antes de usar os exemplos de produção. Considere todas as réplicas ao dimensionar CPU e memória; o proxy deve aceitar pelo menos 90 segundos, com margem adicional para rede e inicialização. Os testes exercitam 20 uploads sintéticos simultâneos como cenário de validação, sem representar um teto de uploads nem uma promessa de capacidade ilimitada: a capacidade real depende dos recursos disponíveis e o backpressure protege o serviço sob sobrecarga.

```bash
python -m pip install -r backend/requirements-dev.txt
python -m compileall backend/app
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
npm test
```

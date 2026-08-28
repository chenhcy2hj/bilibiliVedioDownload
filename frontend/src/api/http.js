// 网络层唯一入口：统一 fetch 封装，解析后端错误结构 {code, message, data}
// 打包版：launcher 以 ?token=xxx 打开页面 → 全部请求携带 X-Auth-Token
const BASE = '/api'

const params = new URLSearchParams(location.search)
const TOKEN = params.get('token') || ''

export async function http(method, path, body) {
  const opts = { method, headers: {} }
  if (TOKEN) opts.headers['X-Auth-Token'] = TOKEN
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const resp = await fetch(BASE + path, opts)
  const contentType = resp.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await resp.json() : null
  if (!resp.ok) {
    const err = new Error(data?.message || `HTTP ${resp.status}`)
    err.code = data?.code || 'HTTP_ERROR'
    err.status = resp.status
    throw err
  }
  return data
}

export const get = (p) => http('GET', p)
export const post = (p, b) => http('POST', p, b)
export const put = (p, b) => http('PUT', p, b)
export const del = (p) => http('DELETE', p)
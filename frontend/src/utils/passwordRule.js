// 与后端Python按Unicode字符计数的6–32限制一致，表情不按两个UTF-16单元计数。
export function passwordLengthRule(_rule, value, callback) {
  const length = typeof value === 'string' ? Array.from(value).length : 0
  callback(length >= 6 && length <= 32 ? undefined : new Error('密码长度 6-32 个字符'))
}

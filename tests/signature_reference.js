// Independent JavaScript oracle for Python's encodeURIComponent/signature parity.
// This contains only synthetic fixture input and the public app's protocol constants.
const crypto = require('node:crypto');
const params = {mail: 'synthetic+test@example.invalid', data: {package: [1, 2, 255]}, flag: true};
const timestamp = 1700000000;
const decode = a => a.map((v, i) => String.fromCharCode(v-i)).join('');
const data = {...params, _platform:'android', _system:'Android', _brand:'NBPower',
  _model:'Home Assistant', _businessID:2, _locale:'en', _version:'2.0.16',
  _versionCode:20016, _proj:decode([78,67,82,114,123,106,120]), _sig_ts:timestamp};
const canonical = Object.keys(data).sort().map(k => k + '=' + encodeURIComponent(
  typeof data[k] === 'object' ? JSON.stringify(data[k]) : data[k])).join('&');
const prefix = decode([65,69,119,111,79,80,74,45,88,124,114,66,80,88,71,99]);
const signature = crypto.createHash('md5').update(prefix+'&'+canonical).digest('hex').slice(8,24);
console.log(JSON.stringify({params,timestamp,signature},null,2));

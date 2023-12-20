use bitbazaar::{err, errors::TracedErr};
use serde_json::Value;

use super::raw_conf::Coerce;

pub fn coerce(value: Value, c_type: Option<Coerce>) -> Result<Value, TracedErr> {
    // Always strip whitespace from string inputs:
    let value = match value {
        Value::String(s) => Value::String(s.trim().to_string()),
        _ => value,
    };

    if let Some(c_type) = c_type {
        // Get a formatted version for the error case:
        let stringified = format!("{:?}", value);

        let result = match c_type {
            Coerce::Json => match value {
                Value::String(s) => match serde_json::from_str(&s) {
                    Ok(v) => Ok(v),
                    Err(e) => Err(err!("Failed to parse string as valid json: {}, {}", s, e)),
                },
                _ => Err(err!("String input expected for json.")),
            },
            Coerce::Str => {
                if matches!(value, Value::String(_)) {
                    Ok(value)
                } else {
                    Ok(Value::String(value.to_string()))
                }
            }
            Coerce::Int => match value {
                Value::Number(num) => Ok(
                    Value::Number((num.as_f64().ok_or_else(||
                        err!("Failed to coerce number to f64.")
                    )?.round() as i64).into())
                ),
                Value::String(s) => Ok(
                    Value::Number((s.parse::<f64>().map_err(|e|
                        err!("String was not a valid int or float: '{}'", e)
                    )?.round() as i64).into())
                ),
                _ => Err(err!(
                    "Ints can only be coerced from ints, floats and strings."
                )),
            },
            Coerce::Float => match value {
                Value::Number(num) => Ok(Value::Number(num)),
                Value::String(s) => Ok(
                    Value::Number(serde_json::Number::from_f64(s.parse::<f64>().map_err(|e|
                        err!("String was not a valid int or float: '{}'", e)
                    )?).ok_or_else(
                        || err!("Failed to coerce float to f64.")
                    )?)
                ),
                _ => Err(err!(
                    "Floats can only be coerced from floats, ints and strings."
                )),
            },
            Coerce::Bool => match value {
                Value::Bool(b) => Ok(Value::Bool(b)),
                Value::Number(num) => match num.to_string().as_str() {
                    "0" => Ok(Value::Bool(false)),
                    "1" => Ok(Value::Bool(true)),
                    _ => Err(err!("Bools can only be coerced from 0/1 integer types.")),
                },
                Value::String(s) => match s.to_lowercase().as_str() {
                    "1" => Ok(Value::Bool(true)),
                    "true" => Ok(Value::Bool(true)),
                    "y" => Ok(Value::Bool(true)),
                    "false" => Ok(Value::Bool(false)),
                    "n" => Ok(Value::Bool(false)),
                    "0" => Ok(Value::Bool(false)),
                    _ => Err(err!(
                        "Bools can only be coerced from strings 'true'/'false'/'y'/'n'/'0'/'1' string types."
                    )),
                },
                _ => Err(err!("Bools can only be coerced from bools, floats and strings.")),
            },
        };

        match result {
            Ok(v) => Ok(v),
            Err(e) => Err(e.modify_msg(|msg| {
                format!(
                    "Failed to coerce to type: '{:?}'.\n{}\nInput: '{}'",
                    c_type,
                    // Max out at 300 chars, adding ... at the end:
                    stringified.chars().take(300).collect::<String>()
                        + if stringified.len() > 300 { "..." } else { "" },
                    msg
                )
            })),
        }
    } else {
        Ok(value)
    }
}

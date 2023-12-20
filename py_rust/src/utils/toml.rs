use bitbazaar::errors::TracedErr;

/// Update a toml file with a json patch and remove some paths
/// * `initial` - The toml input as a string
/// * `update` - A json patch to apply to the toml input, overwrites anything existing, adds anything missing from the patch
/// * `remove` - A list of paths to remove from the toml, applied after update. E.g. [["ctx", "foo"], ["ctx", "bar"]] would remove ctx.foo and ctx.bar from the toml file.
pub fn update(
    initial: &str,
    update: Option<serde_json::Value>,
    remove: Option<Vec<Vec<String>>>,
) -> Result<String, TracedErr> {
    let mut jsonified: serde_json::Value = toml::from_str(initial)?;

    if let Some(update) = update {
        json_patch::merge(&mut jsonified, &update);
    }

    if let Some(remove) = remove {
        for path in remove {
            if !path.is_empty() {
                let mut depth_obj = &mut jsonified;
                for (index, key) in path.iter().enumerate() {
                    if index == path.len() - 1 {
                        if let Some(obj) = depth_obj.as_object_mut() {
                            obj.remove(key);
                        }
                    } else if let Some(obj) = depth_obj.get_mut(key) {
                        depth_obj = obj;
                    } else {
                        break;
                    }
                }
            }
        }
    }

    Ok(toml::to_string_pretty(&jsonified)?)
}

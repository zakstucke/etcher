use bitbazaar::{err, errors::TracedErr};

use crate::args::RenderCommand;

pub fn args_validate(args: &RenderCommand) -> Result<(), TracedErr> {
    // Check the root path exists:
    if !args.root.exists() {
        return Err(err!("Root path does not exist: {}", args.root.display()));
    }

    // Check the root path is a directory rather than a file:
    if !args.root.is_dir() {
        return Err(err!(
            "Root path is not a directory: {}",
            args.root.display()
        ));
    }

    Ok(())
}
